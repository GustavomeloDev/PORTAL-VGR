"""
Processamento em lote do CSV de agendamento PRODESP (menos round-trips ao banco).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Optional

from prodesp.prodesp.agendamento_csv_validacao import (
    MSG_DUPLICATA_VGR,
    data_agendamento_anterior_hoje,
    validar_agendamento_csv_linha,
)
from prodesp.prodesp.blueprint.agendamento_csv_notifier import (
    AgendamentoCsvLinha,
    erro_linha,
    linha_from_row,
)
from prodesp.prodesp.historico import registrar_logs_lote
from prodesp.prodesp.sensitive_fields_crypto import (
    decrypt_sensitive_row_inplace,
    encrypt_sensitive_db_column,
    sensitive_values_equal_for_db,
)

_IN_CHUNK = 500


@dataclass
class AgendamentoCsvImportResult:
    updated_count: int = 0
    sucessos: list[AgendamentoCsvLinha] = field(default_factory=list)
    repetidos: list[AgendamentoCsvLinha] = field(default_factory=list)
    erros: list[AgendamentoCsvLinha] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pending_logs: list[tuple] = field(default_factory=list)


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _carregar_unidades_por_vgr(cursor, vgr_list: list[str]) -> dict[str, dict[str, Any]]:
    if not vgr_list:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for parte in _chunks(vgr_list, _IN_CHUNK):
        placeholders = ",".join(["%s"] * len(parte))
        cursor.execute(
            f"""
            SELECT id_unidades, id_vgr_unidades, data_agendamento_unidades, hora_agendamento_unidades,
                   contratada_planejada_unidades, field_planejada_unidades, contato_field_planejada_unidades
            FROM unidades
            WHERE id_vgr_unidades IN ({placeholders})
            """,
            tuple(parte),
        )
        for row in cursor.fetchall() or []:
            decrypt_sensitive_row_inplace(row)
            vgr = str(row.get("id_vgr_unidades") or "").strip()
            if vgr:
                out[vgr] = row
    return out


def _carregar_ultima_data_concluido_por_unidade(
    cursor, id_unidades: list[int]
) -> dict[int, date]:
    if not id_unidades:
        return {}
    out: dict[int, date] = {}
    for parte in _chunks(id_unidades, _IN_CHUNK):
        placeholders = ",".join(["%s"] * len(parte))
        cursor.execute(
            f"""
            SELECT id_unidades_atendimentos, MAX(data_atendimentos) AS data_concluido
            FROM atendimentos
            WHERE id_unidades_atendimentos IN ({placeholders})
              AND LOWER(TRIM(status_atendimentos)) IN ('concluido', 'concluído')
            GROUP BY id_unidades_atendimentos
            """,
            tuple(parte),
        )
        for row in cursor.fetchall() or []:
            uid = row.get("id_unidades_atendimentos")
            bruto = row.get("data_concluido")
            if uid is None or bruto is None:
                continue
            if isinstance(bruto, datetime):
                out[int(uid)] = bruto.date()
            elif isinstance(bruto, date):
                out[int(uid)] = bruto
            else:
                try:
                    out[int(uid)] = datetime.strptime(str(bruto)[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
    return out


def _queue_log(
    pending: list[tuple],
    id_unidade: int,
    campo: str,
    antigo,
    novo,
) -> None:
    pending.append(
        (
            "unidades",
            id_unidade,
            campo,
            antigo,
            novo,
            "UPDATE",
        )
    )


def processar_importacao_agendamento_csv(
    conn,
    cursor,
    body: list[dict[str, Any]],
    hoje_sp: date,
    *,
    user_re: str,
    user_nome: str,
    normalize_hora_fn: Callable,
    horas_equivalent_fn: Callable,
    format_hora_input_fn: Callable,
    time_from_value_fn: Callable,
    mensagem_bloqueio_concluido_fn: Callable[[date], str],
) -> AgendamentoCsvImportResult:
    """Valida e aplica agendamentos com prefetch em lote."""
    result = AgendamentoCsvImportResult()
    vgr_vistos: set[str] = set()
    fila: list[dict[str, Any]] = []

    for row in body:
        linha_ctx = linha_from_row(row)
        id_vgr = linha_ctx.id_vgr
        data_agendamento = linha_ctx.data_agendamento
        hora_agendamento = linha_ctx.hora_agendamento
        contratada = linha_ctx.contratada
        field_planejado = linha_ctx.field
        contato_field = linha_ctx.contato_field

        tem_agenda = bool(data_agendamento or hora_agendamento)
        tem_planejado = bool(contratada or field_planejado or contato_field)
        if not id_vgr or (not tem_agenda and not tem_planejado):
            continue

        id_vgr_norm = str(id_vgr).strip()
        if id_vgr_norm in vgr_vistos:
            msg = MSG_DUPLICATA_VGR
            result.errors.append(f"VGR {id_vgr_norm}: {msg}")
            result.erros.append(erro_linha(linha_ctx, msg))
            continue
        vgr_vistos.add(id_vgr_norm)

        err_linha, hora_norm_csv, contratada_canonica, contato_norm = validar_agendamento_csv_linha(
            id_vgr=id_vgr_norm,
            data_agendamento=data_agendamento,
            hora_agendamento=hora_agendamento,
            contratada=contratada,
            field_planejado=field_planejado,
            contato_field=contato_field,
            tem_agenda=tem_agenda,
            normalize_hora_fn=normalize_hora_fn,
        )
        if err_linha:
            result.errors.append(f"VGR {id_vgr_norm}: {err_linha}")
            result.erros.append(erro_linha(linha_ctx, err_linha))
            continue

        if data_agendamento:
            msg_data = data_agendamento_anterior_hoje(data_agendamento, hoje_sp)
            if msg_data:
                result.errors.append(f"VGR {id_vgr_norm}: {msg_data}")
                result.erros.append(erro_linha(linha_ctx, msg_data))
                continue

        fila.append(
            {
                "linha_ctx": linha_ctx,
                "id_vgr_norm": id_vgr_norm,
                "data_agendamento": data_agendamento,
                "hora_agendamento": hora_agendamento,
                "tem_agenda": tem_agenda,
                "hora_norm_csv": hora_norm_csv,
                "contratada_canonica": contratada_canonica,
                "field_planejado": field_planejado,
                "contato_norm": contato_norm,
            }
        )

    if not fila:
        return result

    vgr_list = [item["id_vgr_norm"] for item in fila]
    unidades_map = _carregar_unidades_por_vgr(cursor, vgr_list)

    ids_agenda: list[int] = []
    for item in fila:
        if not item["tem_agenda"]:
            continue
        unidade = unidades_map.get(item["id_vgr_norm"])
        if unidade:
            ids_agenda.append(int(unidade["id_unidades"]))
    concluido_map = _carregar_ultima_data_concluido_por_unidade(cursor, ids_agenda)

    for item in fila:
        linha_ctx = item["linha_ctx"]
        id_vgr_norm = item["id_vgr_norm"]
        id_vgr = linha_ctx.id_vgr
        data_agendamento = item["data_agendamento"]
        hora_agendamento = item["hora_agendamento"]
        tem_agenda = item["tem_agenda"]
        hora_norm_csv = item["hora_norm_csv"]
        contratada_canonica = item["contratada_canonica"]
        field_planejado = item["field_planejado"]
        contato_norm = item["contato_norm"]

        try:
            unidade = unidades_map.get(id_vgr_norm)
            if not unidade:
                msg = "Unidade não encontrada (ID VGR inexistente na base)."
                result.errors.append(f"VGR {id_vgr}: {msg}")
                result.erros.append(erro_linha(linha_ctx, msg))
                continue

            id_unidade = int(unidade["id_unidades"])
            old_data = unidade["data_agendamento_unidades"]
            old_hora = unidade["hora_agendamento_unidades"]
            row_updated = False

            if tem_agenda:
                data_concluido = concluido_map.get(id_unidade)
                if data_concluido is not None:
                    msg = mensagem_bloqueio_concluido_fn(data_concluido)
                    result.errors.append(f"VGR {id_vgr}: {msg}")
                    result.erros.append(erro_linha(linha_ctx, msg))
                    continue

            hora_norm = hora_norm_csv
            if hora_norm is None and hora_agendamento:
                hora_norm = normalize_hora_fn(hora_agendamento)

            sets: list[str] = []
            params: list[Any] = []

            if hora_norm and not horas_equivalent_fn(hora_norm, old_hora):
                sets.append("hora_agendamento_unidades = %s")
                params.append(hora_norm)
                _queue_log(
                    result.pending_logs,
                    id_unidade,
                    "hora_agendamento_unidades",
                    old_hora,
                    hora_norm,
                )
                row_updated = True

            if data_agendamento:
                old_data_str = old_data.strftime("%Y-%m-%d") if old_data else ""
                if old_data_str != data_agendamento:
                    sets.append("data_agendamento_unidades = %s")
                    params.append(data_agendamento)
                    _queue_log(
                        result.pending_logs,
                        id_unidade,
                        "data_agendamento_unidades",
                        old_data,
                        data_agendamento,
                    )
                    row_updated = True

            if contratada_canonica is not None:
                old_val = unidade.get("contratada_planejada_unidades")
                if (old_val or "") != contratada_canonica:
                    sets.append("contratada_planejada_unidades = %s")
                    params.append(contratada_canonica)
                    _queue_log(
                        result.pending_logs,
                        id_unidade,
                        "contratada_planejada_unidades",
                        old_val,
                        contratada_canonica,
                    )
                    row_updated = True

            if field_planejado is not None:
                old_val = unidade.get("field_planejada_unidades")
                if (old_val or "") != field_planejado:
                    sets.append("field_planejada_unidades = %s")
                    params.append(field_planejado)
                    _queue_log(
                        result.pending_logs,
                        id_unidade,
                        "field_planejada_unidades",
                        old_val,
                        field_planejado,
                    )
                    row_updated = True

            if contato_norm is not None:
                old_val = unidade.get("contato_field_planejada_unidades")
                if not sensitive_values_equal_for_db(
                    "contato_field_planejada_unidades", contato_norm, old_val
                ):
                    enc_contato = encrypt_sensitive_db_column(
                        "contato_field_planejada_unidades", contato_norm
                    )
                    sets.append("contato_field_planejada_unidades = %s")
                    params.append(enc_contato)
                    _queue_log(
                        result.pending_logs,
                        id_unidade,
                        "contato_field_planejada_unidades",
                        old_val,
                        enc_contato,
                    )
                    row_updated = True

            if sets:
                params.append(id_unidade)
                cursor.execute(
                    f"UPDATE unidades SET {', '.join(sets)} WHERE id_unidades = %s",
                    tuple(params),
                )

            if row_updated:
                result.updated_count += 1
                result.sucessos.append(
                    AgendamentoCsvLinha(
                        id_vgr=id_vgr,
                        data_agendamento=data_agendamento
                        or (old_data.strftime("%Y-%m-%d") if old_data else None),
                        hora_agendamento=(
                            format_hora_input_fn(hora_norm)
                            if hora_norm
                            else hora_agendamento
                        )
                        or (
                            format_hora_input_fn(old_hora)
                            if old_hora
                            else None
                        ),
                        contratada=contratada_canonica
                        or unidade.get("contratada_planejada_unidades"),
                        field=field_planejado or unidade.get("field_planejada_unidades"),
                        contato_field=contato_norm
                        or unidade.get("contato_field_planejada_unidades"),
                        detalhe="Registro atualizado com sucesso.",
                    )
                )
            else:
                data_rep = (
                    old_data.strftime("%Y-%m-%d") if old_data else data_agendamento
                )
                if old_hora is not None:
                    th = time_from_value_fn(old_hora)
                    hora_rep = th.strftime("%H:%M") if th else str(old_hora)[:5]
                else:
                    hora_rep = hora_agendamento
                result.repetidos.append(
                    AgendamentoCsvLinha(
                        id_vgr=id_vgr,
                        data_agendamento=data_rep,
                        hora_agendamento=hora_rep,
                        contratada=unidade.get("contratada_planejada_unidades"),
                        field=unidade.get("field_planejada_unidades"),
                        contato_field=unidade.get("contato_field_planejada_unidades"),
                        detalhe="Mesma data/hora ou dados já cadastrados (sem alteração).",
                    )
                )
        except Exception:
            msg = "Erro ao processar o registro."
            result.errors.append(f"VGR {id_vgr}: {msg}")
            result.erros.append(erro_linha(linha_ctx, msg))

    if result.pending_logs:
        registrar_logs_lote(
            conn,
            result.pending_logs,
            re_user=user_re,
            name_user=user_nome,
        )

    return result
