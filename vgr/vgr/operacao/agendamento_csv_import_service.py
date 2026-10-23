"""
Processamento em lote do CSV de agendamento VGR — criação direta como «Agendado».

Atalho em lote do botão «Confirmar Agendado» (repo_agendamento.confirmar_agendado),
no espírito do CSV PRODESP: a unidade entra na fila de Atendimentos como
«Agendado / Sem atendimento Iniciado». A tela de Agendamentos continua igual.

Por linha com data + hora (+ contratada):
  1. (id_vgr, tipo_servico) → equipamento → unidade. Se o equipamento com esse
     ID VGR estiver sem tipo de serviço, o CSV completa `equipamentos.tipo_servico`
     (nunca sobrescreve um tipo já cadastrado);
  2. agenda aberta da unidade → atualiza data/hora/contratada e promove para
     «Agendado»; sem agenda aberta → cria agenda já em «Agendado»;
  3. sem atendimento vinculado → cria atendimento 1→1 (P4) em
     «Em Atendimento / Aguarda Gestão», não iniciado (P13), igual ao Confirmar Agendado;
  4. Field (opcional) → find-or-create em `fields` + snapshot na agenda e no atendimento.

Linhas só de planejamento (sem data/hora) mantêm a regra PRODESP: atualizam
contratada/Field da agenda aberta sem publicar «Agendado».

Bloqueios: unidade inativa · atendimento Concluído · HA sem 2× SDWAN (P12) ·
outro atendimento ativo fora desta agenda · reagendar atendimento já iniciado ·
data < hoje.

Transação: o caller faz commit/rollback. Cada linha roda em SAVEPOINT.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Iterable

from vgr.vgr.operacao.agendamento_csv_notifier import (
    AgendamentoCsvLinha,
    erro_linha,
    linha_from_row,
)
from vgr.vgr.operacao.agendamento_csv_validacao import (
    CONTRATADAS_CSV_PERMITIDAS,
    MSG_DUPLICATA_VGR,
    MSG_UNIDADE_REPETIDA,
    chave_contratada,
    csv_valor_ausente,
    data_agendamento_anterior_hoje,
    validar_agendamento_csv_linha,
)
from vgr.vgr.operacao.catalogo_agendamento import (
    STATUS_AGENDADO,
    STATUS_DEFAULT,
    STATUS_IMPRODUTIVA,
)

log = logging.getLogger("VGR.agendamento_csv")

_IN_CHUNK = 500
_SAVEPOINT = "vgr_csv_ag_row"

# Agenda encerrada: não recebe CSV — o CSV cria uma agenda nova (P3).
STATUS_AGENDA_ENCERRADOS: tuple[str, ...] = (
    STATUS_IMPRODUTIVA,
    "Agendamento concluído",
    "Finalizado",
)
# Status anteriores a «Agendado»: o CSV promove para «Agendado».
# Os posteriores (Técnico em deslocamento/atendimento) não regridem.
STATUS_AGENDA_PRE_AGENDADO: frozenset[str] = frozenset(
    {
        STATUS_DEFAULT,
        "Aguardando retorno logística",
        "Aguardando retorno fornecedor",
    }
)

# Atendimento criado pela publicação (espelho de confirmar_agendado).
ATEND_STATUS_INICIAL = "Em Atendimento"
ATEND_SUBSTATUS_INICIAL = "Aguarda Gestão"
ATEND_STATUS_FINAIS: tuple[str, ...] = ("Concluído", "Concluído Parcial", "Quebra")


class _LinhaBloqueada(Exception):
    """Regra de negócio detectada dentro do SAVEPOINT (desfaz a linha)."""


@dataclass
class AgendamentoCsvImportResult:
    agendados_count: int = 0
    atendimentos_criados: int = 0
    updated_count: int = 0
    created_count: int = 0
    sucessos: list[AgendamentoCsvLinha] = field(default_factory=list)
    repetidos: list[AgendamentoCsvLinha] = field(default_factory=list)
    erros: list[AgendamentoCsvLinha] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _key_vgr(id_vgr: Any) -> str:
    return str(id_vgr or "").strip().upper()


def _hora_db_str(value: Any) -> str | None:
    """TIME do MySQL (timedelta/time/str) → 'HH:MM:SS'."""
    if value is None or value == "":
        return None
    if isinstance(value, timedelta):
        total = max(0, int(value.total_seconds()))
        hh, rem = divmod(total, 3600)
        mm, ss = divmod(rem, 60)
        return f"{hh:02d}:{mm:02d}:{ss:02d}"
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    s = str(value).strip()
    return s + ":00" if len(s) == 5 else s[:8]


def _data_db_str(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def mensagem_bloqueio_concluido(data_concluido: date | None) -> str:
    if data_concluido:
        return (
            "Unidade já possui atendimento concluído "
            f"(último em {data_concluido.strftime('%d/%m/%Y')}). Agendamento via CSV bloqueado."
        )
    return "Unidade já possui atendimento concluído. Agendamento via CSV bloqueado."


def _in_query(cursor, sql_tpl: str, ids: list, extra: tuple = ()) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for parte in _chunks(ids, _IN_CHUNK):
        placeholders = ",".join(["%s"] * len(parte))
        cursor.execute(sql_tpl.format(ph=placeholders), tuple(parte) + extra)
        out.extend(cursor.fetchall() or [])
    return out


# ---------------------------------------------------------------------------
# Prefetch (poucos round-trips)
# ---------------------------------------------------------------------------


def _carregar_equipamentos(cursor, vgr_list: list[str]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    if not vgr_list:
        return out
    rows = _in_query(
        cursor,
        """
        SELECT e.id_equipamento, e.id_unidade, e.id_vgr, e.tipo_servico, e.ativo,
               u.id_cliente, u.nome_unidade, u.ativo AS unidade_ativa, u.ha
        FROM equipamentos e
        INNER JOIN unidades u ON u.id_unidade = e.id_unidade
        WHERE e.id_vgr IN ({ph})
        ORDER BY e.ativo DESC, e.id_equipamento ASC
        """,
        vgr_list,
    )
    for row in rows:
        out.setdefault(_key_vgr(row.get("id_vgr")), []).append(row)
    return out


def _carregar_sdwan_ativos(cursor, id_unidades: list[int]) -> dict[int, int]:
    if not id_unidades:
        return {}
    rows = _in_query(
        cursor,
        """
        SELECT id_unidade, COUNT(*) AS n
        FROM equipamentos
        WHERE id_unidade IN ({ph}) AND ativo = 1 AND tipo_servico = 'SDWAN'
        GROUP BY id_unidade
        """,
        id_unidades,
    )
    return {int(r["id_unidade"]): int(r["n"]) for r in rows}


def _carregar_concluidos(cursor, id_unidades: list[int]) -> dict[int, date | None]:
    if not id_unidades:
        return {}
    rows = _in_query(
        cursor,
        """
        SELECT id_unidade, MAX(COALESCE(fechamento, atualizado_em)) AS data_concluido
        FROM atendimentos
        WHERE id_unidade IN ({ph})
          AND ativo = 1
          AND LOWER(TRIM(status_atendimento)) IN ('concluído', 'concluido')
        GROUP BY id_unidade
        """,
        id_unidades,
    )
    return {int(r["id_unidade"]): _to_date(r.get("data_concluido")) for r in rows}


def _carregar_agendas_abertas(cursor, id_unidades: list[int]) -> dict[int, dict[str, Any]]:
    """Agenda aberta mais recente por unidade (ativa e não encerrada)."""
    if not id_unidades:
        return {}
    encerrados = ",".join(["%s"] * len(STATUS_AGENDA_ENCERRADOS))
    rows = _in_query(
        cursor,
        f"""
        SELECT id_agendamento, id_unidade, status_agendamento, substatus_agendamento,
               data_agendamento, hora_agendamento, analista_destino, id_contratada_planejada
        FROM agendamentos
        WHERE id_unidade IN ({{ph}})
          AND ativo = 1
          AND status_agendamento NOT IN ({encerrados})
        ORDER BY id_agendamento DESC
        """,
        id_unidades,
        STATUS_AGENDA_ENCERRADOS,
    )
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        out.setdefault(int(row["id_unidade"]), row)
    return out


def _carregar_atendimentos(
    cursor, id_unidades: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Todos os atendimentos das unidades (para 1→1 e conflitos)."""
    if not id_unidades:
        return {}
    rows = _in_query(
        cursor,
        """
        SELECT id_atendimento, id_unidade, id_agendamento, status_atendimento,
               substatus_atendimento, atendimento_iniciado, ativo
        FROM atendimentos
        WHERE id_unidade IN ({ph})
        ORDER BY id_atendimento DESC
        """,
        id_unidades,
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(int(row["id_unidade"]), []).append(row)
    return out


def _carregar_fields_por_nome(cursor, nomes: list[str]) -> dict[str, dict[str, Any]]:
    if not nomes:
        return {}
    rows = _in_query(
        cursor,
        """
        SELECT id_field, nome, telefone
        FROM fields
        WHERE ativo = 1 AND nome IN ({ph})
        ORDER BY id_field ASC
        """,
        nomes,
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out.setdefault(str(row["nome"]).strip().lower(), row)
    return out

def _resolver_contratadas_csv(
    cursor, chaves_usadas: set[str]
) -> tuple[dict[str, int], dict[int, str]]:
    """
    Mapeia as contratadas aceitas no CSV (CONTRATADAS_CSV_PERMITIDAS) para
    `contratadas.id_contratada`, casando por chave normalizada (prefere ativa,
    depois o menor id). Contratada usada no arquivo e ausente no banco é
    cadastrada (ativo=1) na transação do upload, para que
    `agendamentos.id_contratada_planejada` sempre receba um id válido.

    Retorna (id_por_chave, nome_por_id). `nome_por_id` cobre todo o cadastro
    (histórico de contratada antiga) e usa o nome canônico para as da lista.
    """
    cursor.execute(
        """
        SELECT id_contratada, nome_contratada, ativo
        FROM contratadas
        ORDER BY ativo DESC, id_contratada ASC
        """
    )
    rows = cursor.fetchall() or []
    nome_por_id: dict[int, str] = {
        int(r["id_contratada"]): str(r["nome_contratada"]).strip() for r in rows
    }
    id_por_chave_banco: dict[str, int] = {}
    for r in rows:
        id_por_chave_banco.setdefault(
            chave_contratada(r["nome_contratada"]), int(r["id_contratada"])
        )

    id_por_chave: dict[str, int] = {}
    for nome in CONTRATADAS_CSV_PERMITIDAS:
        chave = chave_contratada(nome)
        id_c = id_por_chave_banco.get(chave)
        if id_c is None:
            if chave not in chaves_usadas:
                continue  # não cria cadastro que o arquivo não usa
            cursor.execute(
                "INSERT INTO contratadas (nome_contratada, cnpj, ativo) VALUES (%s, NULL, 1)",
                (nome,),
            )
            id_c = int(cursor.lastrowid)
            log.info("vgr - contratada «%s» cadastrada via CSV de agendamento (#%s)", nome, id_c)
        id_por_chave[chave] = id_c
        nome_por_id[id_c] = nome
    return id_por_chave, nome_por_id


def _atendimento_ativo(at: dict[str, Any]) -> bool:
    return int(at.get("ativo") or 0) == 1 and (
        str(at.get("status_atendimento") or "").strip() not in ATEND_STATUS_FINAIS
    )


# ---------------------------------------------------------------------------
# Escritas (sempre no cursor da transação do caller)
# ---------------------------------------------------------------------------


def _hist(pending: list[tuple], *, user_re, user_nome, tabela: str, id_registro: int,
          id_cliente, id_unidade, campo: str, antigo, novo, operacao: str = "UPDATE") -> None:
    pending.append(
        (
            user_re,
            user_nome,
            tabela,
            id_registro,
            id_cliente,
            id_unidade,
            campo,
            None if antigo is None else str(antigo),
            None if novo is None else str(novo),
            operacao,
        )
    )


def _flush_hist(cursor, pending: list[tuple]) -> None:
    if pending:
        cursor.executemany(
            """
            INSERT INTO historico (
              usuario_re, usuario_nome, tabela_afetada, id_registro, id_cliente, id_unidade,
              campo_alterado, valor_antigo, valor_novo, operacao
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            pending,
        )


def _log_status_agenda(cursor, id_ag: int, ant: str | None, novo: str, *, user_re, user_nome, obs: str) -> None:
    cursor.execute(
        """
        INSERT INTO agendamento_status_log (
          id_agendamento, status_anterior, status_novo, substatus_anterior, substatus_novo,
          usuario_re, usuario_nome, observacao
        ) VALUES (%s, %s, %s, NULL, NULL, %s, %s, %s)
        """,
        (id_ag, ant, novo, user_re, user_nome, obs),
    )


def _criar_atendimento(cursor, *, id_unidade: int, id_agendamento: int, analista,
                       user_re, user_nome, tipo: str) -> int:
    """Espelho de repo_atendimento.create_atendimento p/ status inicial (não iniciado)."""
    cursor.execute(
        """
        INSERT INTO atendimentos (
          id_unidade, id_agendamento, status_atendimento, substatus_atendimento,
          analista_atuante, atendimento_iniciado, abertura, fechamento,
          observacoes, ativo, criado_por_re, atualizado_por_re
        ) VALUES (%s, %s, %s, %s, %s, 0, NULL, NULL, NULL, 1, %s, %s)
        """,
        (id_unidade, id_agendamento, ATEND_STATUS_INICIAL, ATEND_SUBSTATUS_INICIAL,
         analista, user_re, user_re),
    )
    id_at = int(cursor.lastrowid)
    cursor.execute(
        """
        INSERT INTO atendimento_status_log (
          id_atendimento, status_anterior, status_novo, substatus_anterior, substatus_novo,
          usuario_re, usuario_nome, observacao
        ) VALUES (%s, NULL, %s, NULL, %s, %s, %s, %s)
        """,
        (id_at, ATEND_STATUS_INICIAL, ATEND_SUBSTATUS_INICIAL, user_re, user_nome,
         f"create via CSV agendamento ({tipo})"),
    )
    return id_at


def _criar_field(cursor, *, nome: str, telefone, id_contratada, user_re, user_nome) -> int:
    cursor.execute(
        "INSERT INTO fields (nome, telefone, ativo) VALUES (%s, %s, 1)",
        (nome, telefone),
    )
    new_id = int(cursor.lastrowid)
    cursor.execute(
        """
        INSERT INTO field_historico
          (id_field, campo, valor_antigo, valor_novo, usuario_re, usuario_nome)
        VALUES (%s, 'create', NULL, %s, %s, %s)
        """,
        (new_id, f"{nome} (CSV agendamento)", user_re, user_nome),
    )
    if id_contratada:
        cursor.execute(
            "INSERT INTO field_contratadas (id_field, id_contratada, ativo) VALUES (%s, %s, 1)",
            (new_id, id_contratada),
        )
    return new_id


# Whitelist: nunca interpolar nome de tabela vindo de fora.
_SNAP_TABELAS = {
    "agendamento_fields": ("id_agendamento", "id_agendamento_field"),
    "atendimento_fields": ("id_atendimento", "id_atendimento_field"),
}


def _upsert_field_snapshot(cursor, tabela: str, *, id_pai: int, id_field: int, nome: str,
                           telefone, contratada_nome, id_contratada) -> tuple[bool, str | None]:
    """Upsert do snapshot do Field. Retorna (alterou, descricao_antiga)."""
    col_pai, col_pk = _SNAP_TABELAS[tabela]
    cursor.execute(
        f"""
        SELECT {col_pk} AS pk, id_field, ordem, snap_telefone, snap_contratada_nome, id_contratada
        FROM {tabela}
        WHERE {col_pai} = %s
        ORDER BY ordem, {col_pk}
        """,
        (id_pai,),
    )
    vinculos = cursor.fetchall() or []
    atual = next((v for v in vinculos if int(v["id_field"]) == int(id_field)), None)
    if atual:
        tel_old = atual.get("snap_telefone") or None
        cont_old = atual.get("snap_contratada_nome") or None
        tel_new = telefone or tel_old
        cont_new = contratada_nome or cont_old
        if tel_new == tel_old and cont_new == cont_old:
            return False, None
        cursor.execute(
            f"""
            UPDATE {tabela}
            SET snap_telefone = %s, snap_contratada_nome = %s, id_contratada = %s
            WHERE {col_pk} = %s
            """,
            (tel_new, cont_new, id_contratada or atual.get("id_contratada"), atual["pk"]),
        )
        return True, f"{nome} / {tel_old or '—'} / {cont_old or '—'}"

    ordem = max([int(v.get("ordem") or 0) for v in vinculos] + [0]) + 1
    cursor.execute(
        f"""
        INSERT INTO {tabela} (
          {col_pai}, id_field, ordem, snap_nome, snap_telefone, snap_contratada_nome, id_contratada
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (id_pai, id_field, ordem, nome, telefone, contratada_nome, id_contratada),
    )
    return True, None


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def processar_importacao_agendamento_csv(
    cursor,
    body: Iterable[dict[str, Any]],
    hoje_sp: date,
    *,
    contratadas: list[dict[str, Any]] | None = None,
    user_re: str | None,
    user_nome: str | None,
) -> AgendamentoCsvImportResult:
    """Valida e aplica as linhas. ``cursor`` deve ser dictionary=True.

    ``contratadas`` é mantido só por compatibilidade com a rota: a regra do CSV
    é a lista fixa CONTRATADAS_CSV_PERMITIDAS, resolvida no banco por
    _resolver_contratadas_csv.
    """
    result = AgendamentoCsvImportResult()
    nomes_contratadas = list(CONTRATADAS_CSV_PERMITIDAS)

    # ---- 1) Formato + duplicatas no arquivo (sem banco) ----
    chaves_vistas: set[tuple[str, str]] = set()
    fila: list[dict[str, Any]] = []
    for row in body or []:
        if not isinstance(row, dict):
            continue
        linha = linha_from_row(row)
        tem_agenda = bool(linha.data_agendamento or linha.hora_agendamento)
        tem_planejado = not (
            csv_valor_ausente(linha.contratada)
            and csv_valor_ausente(linha.field)
            and csv_valor_ausente(linha.contato_field)
        )
        if not linha.id_vgr or (not tem_agenda and not tem_planejado):
            continue

        err, norm = validar_agendamento_csv_linha(
            id_vgr=linha.id_vgr,
            tipo_servico=linha.tipo_servico,
            data_agendamento=linha.data_agendamento,
            hora_agendamento=linha.hora_agendamento,
            contratada=linha.contratada,
            field_planejado=linha.field,
            contato_field=linha.contato_field,
            tem_agenda=tem_agenda,
            contratadas_permitidas=nomes_contratadas,
        )
        if norm.get("tipo_servico"):
            linha.tipo_servico = norm["tipo_servico"]

        chave = (_key_vgr(linha.id_vgr), linha.tipo_servico or "")
        if chave in chaves_vistas:
            result.erros.append(erro_linha(linha, MSG_DUPLICATA_VGR))
            continue
        chaves_vistas.add(chave)

        if err:
            result.erros.append(erro_linha(linha, err))
            continue
        msg_data = data_agendamento_anterior_hoje(linha.data_agendamento, hoje_sp)
        if msg_data:
            result.erros.append(erro_linha(linha, msg_data))
            continue

        fila.append(
            {
                "linha": linha,
                "tem_agenda": tem_agenda,
                "data": linha.data_agendamento[:10] if linha.data_agendamento else None,
                "hora": norm["hora_norm"],
                "contratada": norm["contratada_canonica"],
                "field_nome": None if csv_valor_ausente(linha.field) else str(linha.field).strip(),
                "contato": norm["contato_norm"],
            }
        )

    if not fila:
        return result
    id_contratada_por_nome, nome_contratada_por_id = _resolver_contratadas_csv(
        cursor,
        {chave_contratada(i["contratada"]) for i in fila if i["contratada"]},
    )

    # ---- 2) Prefetch ----
    eq_map = _carregar_equipamentos(cursor, sorted({_key_vgr(i["linha"].id_vgr) for i in fila}))
    for item in fila:
        candidatos = eq_map.get(_key_vgr(item["linha"].id_vgr)) or []
        tipo = item["linha"].tipo_servico
        exato = next(
            (e for e in candidatos if str(e.get("tipo_servico") or "").strip().upper() == tipo),
            None,
        )
        # Equipamento com o ID VGR mas sem tipo de serviço: o CSV completa o cadastro.
        sem_tipo = next(
            (e for e in candidatos if not str(e.get("tipo_servico") or "").strip()),
            None,
        )
        item["eq"] = exato or sem_tipo
        item["definir_tipo"] = exato is None and sem_tipo is not None
        item["tipos_existentes"] = sorted(
            {str(e.get("tipo_servico")).strip().upper() for e in candidatos if e.get("tipo_servico")}
        )

    ids_unidade = sorted({int(i["eq"]["id_unidade"]) for i in fila if i.get("eq")})
    concluidos = _carregar_concluidos(cursor, ids_unidade)
    sdwan = _carregar_sdwan_ativos(cursor, ids_unidade)
    agendas = _carregar_agendas_abertas(cursor, ids_unidade)
    atendimentos = _carregar_atendimentos(cursor, ids_unidade)
    fields_cache = _carregar_fields_por_nome(
        cursor, sorted({i["field_nome"] for i in fila if i["field_nome"]})
    )

    ctx = dict(
        id_contratada_por_nome=id_contratada_por_nome,
        nome_contratada_por_id=nome_contratada_por_id,
        user_re=user_re,
        user_nome=user_nome,
    )

    # ---- 3) Aplicação linha a linha ----
    unidades_processadas: set[int] = set()
    for item in fila:
        linha: AgendamentoCsvLinha = item["linha"]
        eq = item.get("eq")
        if not eq:
            if item["tipos_existentes"]:
                msg = (
                    f"ID VGR {linha.id_vgr} já está cadastrado como "
                    f"{', '.join(item['tipos_existentes'])} (CSV informou {linha.tipo_servico}). "
                    "Corrija o tipo_servico no CSV ou no cadastro do equipamento."
                )
            else:
                msg = "Unidade não encontrada (ID VGR inexistente na base de equipamentos)."
            result.erros.append(erro_linha(linha, msg))
            continue

        id_unidade = int(eq["id_unidade"])
        if not int(eq.get("unidade_ativa") or 0):
            result.erros.append(erro_linha(linha, "Unidade inativa — reative o cadastro antes de agendar."))
            continue
        if id_unidade in unidades_processadas:
            result.erros.append(erro_linha(linha, MSG_UNIDADE_REPETIDA))
            continue
        if item["tem_agenda"]:
            if id_unidade in concluidos:
                result.erros.append(erro_linha(linha, mensagem_bloqueio_concluido(concluidos[id_unidade])))
                continue
            n_sdwan = sdwan.get(id_unidade, 0)
            if item["definir_tipo"] and linha.tipo_servico == "SDWAN" and int(eq.get("ativo") or 0):
                n_sdwan += 1  # o equipamento passará a contar como SDWAN
            if int(eq.get("ha") or 0) and n_sdwan < 2:
                result.erros.append(erro_linha(
                    linha,
                    "Unidade HA exige 2 equipamentos SDWAN ativos para Agendado "
                    f"(encontrados: {n_sdwan}).",
                ))
                continue

        pending_hist: list[tuple] = []
        novos_fields: dict[str, dict[str, Any]] = {}
        try:
            cursor.execute(f"SAVEPOINT {_SAVEPOINT}")
            msg_eq = None
            if item["definir_tipo"]:
                msg_eq = _definir_tipo_servico_equipamento(
                    cursor,
                    eq=eq,
                    tipo=linha.tipo_servico,
                    pending_hist=pending_hist,
                    user_re=user_re,
                    user_nome=user_nome,
                )
            saida = _aplicar_linha(
                cursor,
                item=item,
                id_unidade=id_unidade,
                id_cliente=eq.get("id_cliente"),
                agenda=agendas.get(id_unidade),
                atendimentos_unidade=atendimentos.get(id_unidade, []),
                fields_cache=fields_cache,
                novos_fields=novos_fields,
                pending_hist=pending_hist,
                **ctx,
            )
            _flush_hist(cursor, pending_hist)
            cursor.execute(f"RELEASE SAVEPOINT {_SAVEPOINT}")
        except _LinhaBloqueada as exc:
            _rollback_savepoint(cursor)
            result.erros.append(erro_linha(linha, str(exc)))
            continue
        except Exception:
            _rollback_savepoint(cursor)
            result.erros.append(erro_linha(linha, "Erro ao processar o registro."))
            continue

        if msg_eq:
            eq["tipo_servico"] = linha.tipo_servico
            if linha.tipo_servico == "SDWAN" and int(eq.get("ativo") or 0):
                sdwan[id_unidade] = sdwan.get(id_unidade, 0) + 1
            saida["detalhe"] = msg_eq + (" " + saida["detalhe"] if saida["alterou"] else "")
            saida["alterou"] = True
        unidades_processadas.add(id_unidade)
        fields_cache.update(novos_fields)
        agendas[id_unidade] = saida["agenda"]
        if saida.get("novo_atendimento"):
            atendimentos.setdefault(id_unidade, []).insert(0, saida["novo_atendimento"])

        ag = saida["agenda"]
        exib = AgendamentoCsvLinha(
            id_vgr=linha.id_vgr,
            tipo_servico=linha.tipo_servico,
            data_agendamento=_data_db_str(ag.get("data_agendamento")),
            hora_agendamento=_hora_db_str(ag.get("hora_agendamento")),
            contratada=nome_contratada_por_id.get(int(ag.get("id_contratada_planejada") or 0))
            or item["contratada"],
            field=item["field_nome"],
            contato_field=item["contato"],
            detalhe=saida["detalhe"],
        )
        if saida["alterou"]:
            result.sucessos.append(exib)
            result.created_count += int(saida.get("agenda_criada", False))
            result.updated_count += int(not saida.get("agenda_criada", False))
            result.agendados_count += int(saida.get("publicou_agendado", False))
            result.atendimentos_criados += int(bool(saida.get("novo_atendimento")))
        else:
            result.repetidos.append(exib)

    return result


def _definir_tipo_servico_equipamento(
    cursor, *, eq: dict[str, Any], tipo: str, pending_hist: list[tuple], user_re, user_nome
) -> str:
    """Completa equipamentos.tipo_servico (vazio) com o valor do CSV.

    Só grava quando o campo está vazio (nunca sobrescreve um tipo já cadastrado).
    Com o tipo preenchido, a unidade aparece nas colunas ID VGR SDWAN/SDWIFI/SDLAN
    da fila de Atendimentos e o modal carrega o inventário pelo ID VGR.
    """
    id_eq = int(eq["id_equipamento"])
    cursor.execute(
        """
        UPDATE equipamentos
        SET tipo_servico = %s
        WHERE id_equipamento = %s AND (tipo_servico IS NULL OR tipo_servico = '')
        """,
        (tipo, id_eq),
    )
    _hist(
        pending_hist,
        user_re=user_re,
        user_nome=user_nome,
        tabela="equipamentos",
        id_registro=id_eq,
        id_cliente=eq.get("id_cliente"),
        id_unidade=int(eq["id_unidade"]),
        campo="tipo_servico",
        antigo=None,
        novo=f"{tipo} (via CSV agendamento — ID VGR {eq.get('id_vgr')})",
    )
    return f"Equipamento #{id_eq} (ID VGR {eq.get('id_vgr')}): tipo de serviço definido como {tipo}."


def _rollback_savepoint(cursor) -> None:
    try:
        cursor.execute(f"ROLLBACK TO SAVEPOINT {_SAVEPOINT}")
    except Exception:
        pass


def _aplicar_linha(
    cursor,
    *,
    item: dict[str, Any],
    id_unidade: int,
    id_cliente,
    agenda: dict[str, Any] | None,
    atendimentos_unidade: list[dict[str, Any]],
    fields_cache: dict[str, dict[str, Any]],
    novos_fields: dict[str, dict[str, Any]],
    pending_hist: list[tuple],
    id_contratada_por_nome: dict[str, int],
    nome_contratada_por_id: dict[int, str],
    user_re,
    user_nome,
) -> dict[str, Any]:
    linha: AgendamentoCsvLinha = item["linha"]
    tipo = linha.tipo_servico
    publicar = bool(item["tem_agenda"])
    id_contratada = (
        id_contratada_por_nome.get(chave_contratada(item["contratada"]))
        if item["contratada"]
        else None
    )
    h = dict(user_re=user_re, user_nome=user_nome, id_cliente=id_cliente, id_unidade=id_unidade)

    alterou = False
    agenda_criada = False
    publicou_agendado = False
    novo_atendimento: dict[str, Any] | None = None
    partes: list[str] = []

    id_ag_atual = int(agenda["id_agendamento"]) if agenda else None
    at_vinculado = next(
        (a for a in atendimentos_unidade if id_ag_atual and int(a.get("id_agendamento") or 0) == id_ag_atual),
        None,
    )

    # ---- Conflitos que impedem publicar «Agendado» ----
    if publicar:
        outro = next(
            (a for a in atendimentos_unidade
             if _atendimento_ativo(a) and (not id_ag_atual or int(a.get("id_agendamento") or 0) != id_ag_atual)),
            None,
        )
        if outro:
            raise _LinhaBloqueada(
                f"Unidade já possui atendimento ativo #{outro['id_atendimento']} "
                f"({outro.get('status_atendimento') or '—'} / {outro.get('substatus_atendimento') or '—'}) "
                "fora desta agenda. Trate-o na fila de Atendimentos."
            )
        if at_vinculado and not _atendimento_ativo(at_vinculado):
            raise _LinhaBloqueada(
                f"Agenda #{id_ag_atual} já possui atendimento #{at_vinculado['id_atendimento']} "
                "inativo/finalizado. Crie nova agenda pela tela de Agendamentos."
            )

    # ---- Agenda: cria já «Agendado» ou atualiza/promove a aberta ----
    if agenda is None:
        status_novo = STATUS_AGENDADO if publicar else STATUS_DEFAULT
        cursor.execute(
            """
            INSERT INTO agendamentos (
              id_unidade, status_agendamento, data_agendamento, hora_agendamento,
              id_contratada_planejada, ativo, criado_por_re, atualizado_por_re
            ) VALUES (%s, %s, %s, %s, %s, 1, %s, %s)
            """,
            (id_unidade, status_novo, item["data"], item["hora"], id_contratada, user_re, user_re),
        )
        id_ag = int(cursor.lastrowid)
        _log_status_agenda(cursor, id_ag, None, status_novo, user_re=user_re, user_nome=user_nome,
                           obs=f"create via CSV ({tipo})")
        _hist(pending_hist, tabela="agendamentos", id_registro=id_ag, campo="csv_agendamento",
              antigo=None, novo=f"criado via CSV como {status_novo} — ID VGR {linha.id_vgr} ({tipo})",
              operacao="INSERT", **h)
        agenda_final = {
            "id_agendamento": id_ag, "id_unidade": id_unidade, "status_agendamento": status_novo,
            "data_agendamento": item["data"], "hora_agendamento": item["hora"],
            "analista_destino": None, "id_contratada_planejada": id_contratada,
        }
        alterou = agenda_criada = True
        publicou_agendado = publicar
        partes.append(f"Agenda #{id_ag} criada como {status_novo} ({tipo}).")
    else:
        id_ag = id_ag_atual
        old_data = _data_db_str(agenda.get("data_agendamento"))
        old_hora = _hora_db_str(agenda.get("hora_agendamento"))
        old_status = str(agenda.get("status_agendamento") or "")
        old_cont = int(agenda.get("id_contratada_planejada") or 0)

        muda_data = bool(item["data"]) and item["data"] != old_data
        muda_hora = bool(item["hora"]) and item["hora"] != old_hora
        if (muda_data or muda_hora) and at_vinculado and int(at_vinculado.get("atendimento_iniciado") or 0):
            raise _LinhaBloqueada(
                f"Atendimento #{at_vinculado['id_atendimento']} já iniciado — "
                "reagendamento deve ser feito pela tela de Agendamentos."
            )

        sets: list[str] = []
        params: list[Any] = []
        if muda_data:
            sets.append("data_agendamento = %s")
            params.append(item["data"])
            _hist(pending_hist, tabela="agendamentos", id_registro=id_ag, campo="data_agendamento",
                  antigo=old_data, novo=item["data"], **h)
        if muda_hora:
            sets.append("hora_agendamento = %s")
            params.append(item["hora"])
            _hist(pending_hist, tabela="agendamentos", id_registro=id_ag, campo="hora_agendamento",
                  antigo=old_hora, novo=item["hora"], **h)
        if id_contratada and old_cont != id_contratada:
            sets.append("id_contratada_planejada = %s")
            params.append(id_contratada)
            _hist(pending_hist, tabela="agendamentos", id_registro=id_ag, campo="contratada_planejada",
                  antigo=nome_contratada_por_id.get(old_cont), novo=item["contratada"], **h)
        status_final = old_status
        if publicar and old_status in STATUS_AGENDA_PRE_AGENDADO:
            sets.append("status_agendamento = %s")
            params.append(STATUS_AGENDADO)
            status_final = STATUS_AGENDADO
            _log_status_agenda(cursor, id_ag, old_status, STATUS_AGENDADO, user_re=user_re,
                               user_nome=user_nome, obs=f"Agendado via CSV ({tipo})")
            publicou_agendado = True
        agenda_final = dict(agenda)
        agenda_final["status_agendamento"] = status_final
        if sets:
            sets.append("atualizado_por_re = %s")
            params.extend([user_re, id_ag])
            cursor.execute(
                f"UPDATE agendamentos SET {', '.join(sets)} WHERE id_agendamento = %s",
                tuple(params),
            )
            if muda_data:
                agenda_final["data_agendamento"] = item["data"]
            if muda_hora:
                agenda_final["hora_agendamento"] = item["hora"]
            if id_contratada:
                agenda_final["id_contratada_planejada"] = id_contratada
            alterou = True
            if publicou_agendado:
                partes.append(f"Agenda #{id_ag} publicada como Agendado ({tipo}).")
            else:
                partes.append(f"Agenda #{id_ag} atualizada ({tipo}).")

    # ---- Atendimento 1→1 (P4) — igual ao Confirmar Agendado ----
    id_at = (
        int(at_vinculado["id_atendimento"])
        if at_vinculado and _atendimento_ativo(at_vinculado)
        else None
    )
    if publicar and not at_vinculado:
        id_at = _criar_atendimento(
            cursor, id_unidade=id_unidade, id_agendamento=id_ag,
            analista=agenda_final.get("analista_destino"), user_re=user_re, user_nome=user_nome, tipo=tipo,
        )
        novo_atendimento = {
            "id_atendimento": id_at, "id_unidade": id_unidade, "id_agendamento": id_ag,
            "status_atendimento": ATEND_STATUS_INICIAL, "substatus_atendimento": ATEND_SUBSTATUS_INICIAL,
            "atendimento_iniciado": 0, "ativo": 1,
        }
        _hist(pending_hist, tabela="atendimentos", id_registro=id_at, campo="csv_agendamento",
              antigo=None, novo=f"criado via CSV (agenda #{id_ag})", operacao="INSERT", **h)
        alterou = True
        partes.append(f"Atendimento #{id_at} criado (não iniciado).")

    # ---- Field planejado: master + snapshot na agenda e no atendimento ----
    if item["field_nome"]:
        nome = item["field_nome"]
        chave = nome.lower()
        f_row = novos_fields.get(chave) or fields_cache.get(chave)
        if f_row is None:
            id_field = _criar_field(cursor, nome=nome, telefone=item["contato"], id_contratada=id_contratada,
                                    user_re=user_re, user_nome=user_nome)
            f_row = {"id_field": id_field, "nome": nome, "telefone": item["contato"]}
            novos_fields[chave] = f_row
            partes.append(f"Field «{nome}» cadastrado.")
        snap = dict(id_field=int(f_row["id_field"]), nome=str(f_row["nome"]), telefone=item["contato"],
                    contratada_nome=item["contratada"], id_contratada=id_contratada)
        mudou, antigo = _upsert_field_snapshot(cursor, "agendamento_fields", id_pai=id_ag, **snap)
        if id_at:
            mudou_at, _ = _upsert_field_snapshot(cursor, "atendimento_fields", id_pai=id_at, **snap)
            mudou = mudou or mudou_at
        if mudou:
            _hist(pending_hist, tabela="agendamentos", id_registro=id_ag, campo="field_planejado",
                  antigo=antigo,
                  novo=f"{f_row['nome']} / {item['contato'] or '—'} / {item['contratada'] or '—'}", **h)
            alterou = True
            partes.append("Dados Field vinculados.")

    detalhe = (
        " ".join(partes) if alterou
        else "Mesma data/hora ou dados já cadastrados (sem alteração)."
    )
    return {
        "alterou": alterou,
        "detalhe": detalhe,
        "agenda": agenda_final,
        "agenda_criada": agenda_criada,
        "publicou_agendado": publicou_agendado,
        "novo_atendimento": novo_atendimento,
    }
