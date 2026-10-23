"""Observações em lote para relatório PRODESP (download + e-mail gestão)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Mapping

# (instante para ordenação, texto da linha, desempate)
EntradaRelatorio = tuple[datetime | None, str, int]

_CHUNK_IDS = 400


def date_range_exclusive(start_date: str, end_date: str) -> tuple[str, str]:
    end = datetime.strptime(str(end_date)[:10], "%Y-%m-%d").date()
    return str(start_date)[:10], (end + timedelta(days=1)).isoformat()


def _ts_para_ordenacao(ts: Any) -> datetime | None:
    if ts is None or ts == "":
        return None
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, date):
        return datetime.combine(ts, datetime.min.time())
    s = str(ts).strip()
    if not s:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ):
        try:
            return datetime.strptime(s[:19], fmt)
        except ValueError:
            continue
    return None


def _format_ts_br(ts: Any) -> str:
    dt = _ts_para_ordenacao(ts)
    if dt:
        return dt.strftime("%d/%m/%Y %H:%M")
    return str(ts or "").strip()


def format_linha_substatus_historico(row: Mapping[str, Any]) -> EntradaRelatorio:
    novo = (row.get("valor_novo_historico") or "").strip()
    ts_raw = row.get("data_alteracao_historico")
    ts_txt = _format_ts_br(ts_raw)
    acao = f"[Substatus] «{novo}»" if novo else "[Substatus] alterado"
    linha = f"{ts_txt}: {acao}"
    seq = int(row.get("id_log_historico") or 0)
    return _ts_para_ordenacao(ts_raw), linha, seq


def carregar_observacoes_map(
    cursor, start_inclusive: str, end_exclusive: str
) -> tuple[dict[int, list[EntradaRelatorio]], dict[int, list[EntradaRelatorio]]]:
    cursor.execute(
        """
        SELECT id_observacoes, id_atendimentos_observacoes, id_unidades_observacoes,
               observacoes, timestamp_observacoes
        FROM observacoes
        WHERE timestamp_observacoes >= %s
          AND timestamp_observacoes < %s
        ORDER BY timestamp_observacoes ASC, id_observacoes ASC
        """,
        (start_inclusive, end_exclusive),
    )
    por_atendimento: dict[int, list[EntradaRelatorio]] = defaultdict(list)
    por_unidade_sem_att: dict[int, list[EntradaRelatorio]] = defaultdict(list)
    for row in cursor.fetchall() or []:
        ts = row.get("timestamp_observacoes")
        ts_txt = _format_ts_br(ts)
        texto = (row.get("observacoes") or "").strip()
        linha = f"{ts_txt}: {texto}" if texto else ts_txt
        entrada: EntradaRelatorio = (
            _ts_para_ordenacao(ts),
            linha,
            int(row.get("id_observacoes") or 0),
        )
        id_att = row.get("id_atendimentos_observacoes")
        id_u = row.get("id_unidades_observacoes")
        if id_att:
            por_atendimento[int(id_att)].append(entrada)
        elif id_u:
            por_unidade_sem_att[int(id_u)].append(entrada)
    return por_atendimento, por_unidade_sem_att


def carregar_substatus_historico_map(
    cursor, ids_atendimento: list[int] | set[int]
) -> dict[int, list[EntradaRelatorio]]:
    """Mudanças de substatus (hora + valor) por atendimento, via tabela historico."""
    ids = sorted({int(i) for i in (ids_atendimento or []) if i is not None and int(i) > 0})
    if not ids:
        return {}

    por_atendimento: dict[int, list[EntradaRelatorio]] = defaultdict(list)
    for offset in range(0, len(ids), _CHUNK_IDS):
        chunk = ids[offset : offset + _CHUNK_IDS]
        placeholders = ", ".join(["%s"] * len(chunk))
        cursor.execute(
            f"""
            SELECT id_log_historico, id_registro_afetado_historico,
                   valor_antigo_historico, valor_novo_historico,
                   usuario_nome_historico, usuario_re_historico,
                   data_alteracao_historico
            FROM historico
            WHERE tabela_afetada_historico = 'atendimentos'
              AND campo_alterado_historico = 'substatus_atendimentos'
              AND id_registro_afetado_historico IN ({placeholders})
            ORDER BY data_alteracao_historico ASC, id_log_historico ASC
            """,
            tuple(chunk),
        )
        for row in cursor.fetchall() or []:
            id_att = row.get("id_registro_afetado_historico")
            if not id_att:
                continue
            por_atendimento[int(id_att)].append(format_linha_substatus_historico(row))
    return dict(por_atendimento)


def _ordenar_entradas_desc(entradas: list[EntradaRelatorio]) -> list[str]:
    """Mais recente em cima; desempate por id de registro."""
    vistos: set[str] = set()
    unicos: list[EntradaRelatorio] = []
    for entrada in entradas:
        linha = entrada[1]
        if linha in vistos:
            continue
        vistos.add(linha)
        unicos.append(entrada)

    def sort_key(e: EntradaRelatorio):
        ts, _, seq = e
        ts_ord = ts or datetime.min
        return (ts_ord, seq)

    unicos.sort(key=sort_key, reverse=True)
    return [e[1] for e in unicos]


def observacoes_linha_relatorio(
    row: Mapping[str, Any],
    por_atendimento: dict[int, list[EntradaRelatorio]],
    por_unidade_sem_att: dict[int, list[EntradaRelatorio]],
    por_substatus: dict[int, list[EntradaRelatorio]] | None = None,
) -> str:
    entradas: list[EntradaRelatorio] = []
    id_att = row.get("id_atendimento") or row.get("id_atendimentos")
    id_u = row.get("id_unidades")
    if id_att:
        id_int = int(id_att)
        entradas.extend(por_atendimento.get(id_int, []))
        if por_substatus:
            entradas.extend(por_substatus.get(id_int, []))
    if id_u:
        entradas.extend(por_unidade_sem_att.get(int(id_u), []))
    return "\n".join(_ordenar_entradas_desc(entradas))
