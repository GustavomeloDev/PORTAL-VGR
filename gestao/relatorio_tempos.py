"""Tempos por etapa e totais para relatório PRODESP (download + e-mail gestão)."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, time
from typing import Any, Mapping

import pytz

from prodesp.prodesp.atendimento_business_rules import (
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_GESTAO,
    SUBSTATUS_AGUARDA_LICENCA,
    SUBSTATUS_AGUARDANDO_CLIENTE,
    SUBSTATUS_COM_SUPORTE,
    SUBSTATUS_INICIAL_FILA,
    SUBSTATUS_LEGACY_TRIAGEM,
)

COL_TEMPO_VITA = "Tempo de Vita"
COL_TEMPO_ATENDIMENTO = "Tempo do Atendimento"

# (rótulo da coluna, substatus no log que compõem a etapa)
ETAPAS_RELATORIO_TEMPO: tuple[tuple[str, tuple[str, ...]], ...] = (
    (SUBSTATUS_AGUARDA_GESTAO, (SUBSTATUS_AGUARDA_GESTAO, SUBSTATUS_LEGACY_TRIAGEM)),
    (SUBSTATUS_COM_SUPORTE, (SUBSTATUS_COM_SUPORTE,)),
    (SUBSTATUS_AGUARDANDO_CLIENTE, (SUBSTATUS_AGUARDANDO_CLIENTE,)),
    (SUBSTATUS_AGUARDA_CONTRATADA, (SUBSTATUS_AGUARDA_CONTRATADA,)),
    (SUBSTATUS_AGUARDA_LICENCA, (SUBSTATUS_AGUARDA_LICENCA,)),
    (SUBSTATUS_INICIAL_FILA, (SUBSTATUS_INICIAL_FILA,)),
    ("Em Configuração Remota", ("Em Configuração Remota",)),
    ("Aguardando Config. MPLS", ("Aguardando Config. MPLS",)),
    ("Em Configuração do MPLS", ("Em Configuração do MPLS",)),
    ("Aguardando Caderno de Teste", ("Aguardando Caderno de Teste",)),
    ("Em Caderno de Teste", ("Em Caderno de Teste",)),
)

# Filas ativas de configuração (exclui Aguardando*, Cliente, Contratada, Licença)
SUBSTATUS_TEMPO_ATENDIMENTO_CONFIG: frozenset[str] = frozenset(
    {
        "Em Configuração Remota",
        "Em Configuração do MPLS",
        "Em Caderno de Teste",
    }
)

_CHUNK_IDS = 400
TZ_SP = pytz.timezone("America/Sao_Paulo")
_HISTORICO_CAMPO_POR_TIPO_LOG = {
    "substatus": "substatus_atendimentos",
    "status": "status_atendimentos",
}


def _log_evento_ja_coberto(
    logs: list[dict[str, Any]], valor_novo: str, alterado_em
) -> bool:
    alvo = (valor_novo or "").strip()
    if not alvo or alterado_em is None:
        return False
    for row in logs:
        if (row.get("valor_novo_log") or "").strip() != alvo:
            continue
        existente = row.get("alterado_em_log")
        if existente is None:
            continue
        if existente == alterado_em:
            return True
    return False


def _mesclar_historico_em_logs(
    cursor,
    por_att: dict[int, list[dict[str, Any]]],
    ids: list[int],
    *,
    tipo_campo: str,
) -> dict[int, list[dict[str, Any]]]:
    """Inclui transições do historico omitidas pela trigger antiga do status_log."""
    campo_hist = _HISTORICO_CAMPO_POR_TIPO_LOG.get(tipo_campo)
    if not campo_hist or not ids:
        return por_att
    for offset in range(0, len(ids), _CHUNK_IDS):
        chunk = ids[offset : offset + _CHUNK_IDS]
        placeholders = ", ".join(["%s"] * len(chunk))
        cursor.execute(
            f"""
            SELECT id_registro_afetado_historico,
                   valor_antigo_historico,
                   valor_novo_historico,
                   data_alteracao_historico
            FROM historico
            WHERE tabela_afetada_historico = 'atendimentos'
              AND campo_alterado_historico = %s
              AND operacao_historico = 'UPDATE'
              AND id_registro_afetado_historico IN ({placeholders})
            ORDER BY id_registro_afetado_historico, data_alteracao_historico
            """,
            (campo_hist, *chunk),
        )
        for row in cursor.fetchall() or []:
            id_att = row.get("id_registro_afetado_historico")
            if not id_att:
                continue
            id_att = int(id_att)
            valor_novo = (row.get("valor_novo_historico") or "").strip()
            if not valor_novo:
                continue
            logs = por_att.setdefault(id_att, [])
            alterado = row.get("data_alteracao_historico")
            if _log_evento_ja_coberto(logs, valor_novo, alterado):
                continue
            logs.append(
                {
                    "id_atendimentos_log": id_att,
                    "tipo_campo_log": tipo_campo,
                    "valor_anterior_log": row.get("valor_antigo_historico"),
                    "valor_novo_log": valor_novo,
                    "alterado_em_log": alterado,
                    "id_log_atendimentos_status": None,
                }
            )
    for id_att in por_att:
        por_att[id_att].sort(
            key=lambda r: (
                r.get("alterado_em_log") or datetime.min,
                r.get("id_log_atendimentos_status") or 0,
            )
        )
    return por_att


def colunas_tempo_etapa() -> list[str]:
    return [f"Tempo {label}" for label, _ in ETAPAS_RELATORIO_TEMPO]


def colunas_inicio_etapa() -> list[str]:
    return [f"Início {label}" for label, _ in ETAPAS_RELATORIO_TEMPO]


def _segundos_para_hms(segundos: float | int) -> str:
    total = max(0, int(segundos))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _normalizar_dt(dt: Any, tz_sp) -> datetime | None:
    if not dt:
        return None
    if hasattr(dt, "to_pydatetime"):
        dt = dt.to_pydatetime()
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return tz_sp.localize(dt)
    return dt.astimezone(tz_sp)


_CHUNK_IDS = 400
TZ_SP = pytz.timezone("America/Sao_Paulo")
_STATUS_FIM_RE = re.compile(r"Quebra|Pendente", re.I)


def _parse_hora_final(val: Any) -> time | None:
    if val is None or val == "":
        return None
    if isinstance(val, time):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s[:8], fmt).time()
        except ValueError:
            continue
    return None


def _parse_data_atendimento(val: Any) -> date | None:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    elif " " in s:
        s = s.split(" ", 1)[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def inferir_fim_corte_atendimento(
    *,
    status_logs: list[Mapping[str, Any]] | None = None,
    data_atendimento: Any = None,
    horario_finalizacao: Any = None,
    status_atendimento: str | None = None,
    tz_sp=None,
) -> datetime | None:
    """
    Instantâneo de encerramento (mesma regra da vw_tempo_atendimento_detalhado):
    log status Concluído, depois Quebra/Pendente, depois horário final do atendimento.
    """
    tz = tz_sp or TZ_SP
    fim: datetime | None = None

    for row in status_logs or []:
        if (row.get("tipo_campo_log") or "").strip() != "status":
            continue
        val = (row.get("valor_novo_log") or "").strip()
        ts = _normalizar_dt(row.get("alterado_em_log"), tz)
        if not ts:
            continue
        if val == "Concluído":
            if fim is None or ts > fim:
                fim = ts
        elif _STATUS_FIM_RE.search(val):
            if fim is None or ts > fim:
                fim = ts

    if fim is not None:
        return fim

    st = (status_atendimento or "").strip()
    if st in ("Concluído", "Quebra", "Quebra TBRA", "Concluído Parcial", "Pendente"):
        dia = _parse_data_atendimento(data_atendimento)
        hora = _parse_hora_final(horario_finalizacao)
        if dia and hora:
            return tz.localize(datetime.combine(dia, hora))
    return None


def _fechar_intervalo(
    start: datetime,
    end: datetime | None,
    *,
    fim_corte: datetime | None,
    agora: datetime,
) -> int:
    if end is None:
        end = fim_corte or agora
    elif fim_corte is not None and end > fim_corte:
        end = fim_corte
    if fim_corte is not None and start > fim_corte:
        return 0
    return max(0, int((end - start).total_seconds()))


def duracao_acumulada_substatus_segundos(
    rows_chrono: list[Mapping[str, Any]],
    substatus_nome: str,
    tz_sp,
    *,
    fim_corte: datetime | None = None,
    agora: datetime | None = None,
) -> int:
    """Soma intervalos em um substatus (fecha em data_fim do atendimento, não em now)."""
    total = 0
    nome = (substatus_nome or "").strip()
    if not nome or not rows_chrono:
        return 0
    tz = tz_sp or TZ_SP
    agora_sp = agora or datetime.now(tz)
    for i, row in enumerate(rows_chrono):
        val = (row.get("valor_novo_log") or "").strip()
        if val != nome:
            continue
        start = _normalizar_dt(row.get("alterado_em_log"), tz)
        if not start:
            continue
        end_raw = rows_chrono[i + 1].get("alterado_em_log") if i + 1 < len(rows_chrono) else None
        end = _normalizar_dt(end_raw, tz) if end_raw else None
        total += _fechar_intervalo(start, end, fim_corte=fim_corte, agora=agora_sp)
    return total


def _inicio_primeira_etapa(
    logs_chrono: list[Mapping[str, Any]], substatus_names: tuple[str, ...], tz_sp
) -> str:
    nomes = frozenset((s or "").strip() for s in substatus_names if (s or "").strip())
    if not nomes or not logs_chrono:
        return ""
    primeiro = None
    for row in logs_chrono:
        val = (row.get("valor_novo_log") or "").strip()
        if val not in nomes:
            continue
        ts = row.get("alterado_em_log")
        if not ts:
            continue
        if primeiro is None or ts < primeiro:
            primeiro = ts
    dt = _normalizar_dt(primeiro, tz_sp)
    return dt.strftime("%H:%M:%S") if dt else ""


def _tempo_acumulado_etapa(
    logs_chrono: list[Mapping[str, Any]],
    substatus_names: tuple[str, ...],
    tz_sp,
    *,
    fim_corte: datetime | None = None,
    agora: datetime | None = None,
) -> str:
    total = 0
    for nome in substatus_names:
        total += duracao_acumulada_substatus_segundos(
            logs_chrono, nome, tz_sp, fim_corte=fim_corte, agora=agora
        )
    return _segundos_para_hms(total)


def metricas_atendimento_logs(
    logs_chrono: list[Mapping[str, Any]],
    tz_sp=None,
    *,
    fim_corte: datetime | None = None,
    agora: datetime | None = None,
) -> dict[str, str]:
    """Totais + tempo por etapa a partir do log de substatus (ordem cronológica)."""
    tz = tz_sp or TZ_SP
    agora_sp = agora or datetime.now(tz)
    logs = sorted(
        list(logs_chrono or []),
        key=lambda r: (
            r.get("alterado_em_log") or datetime.min,
            int(r.get("id_log_atendimentos_status") or 0),
        ),
    )
    out: dict[str, str] = {}
    kw = {"fim_corte": fim_corte, "agora": agora_sp}
    for label, nomes in ETAPAS_RELATORIO_TEMPO:
        out[f"Início {label}"] = _inicio_primeira_etapa(logs, nomes, tz)
        out[f"Tempo {label}"] = _tempo_acumulado_etapa(logs, nomes, tz, **kw)

    vita_seg = 0
    for _, nomes in ETAPAS_RELATORIO_TEMPO:
        for nome in nomes:
            vita_seg += duracao_acumulada_substatus_segundos(logs, nome, tz, **kw)

    vistos = {n for _, nomes in ETAPAS_RELATORIO_TEMPO for n in nomes}
    for row in logs:
        val = (row.get("valor_novo_log") or "").strip()
        if val and val not in vistos:
            vita_seg += duracao_acumulada_substatus_segundos(logs, val, tz, **kw)
            vistos.add(val)

    att_seg = sum(
        duracao_acumulada_substatus_segundos(logs, nome, tz, **kw)
        for nome in SUBSTATUS_TEMPO_ATENDIMENTO_CONFIG
    )
    out[COL_TEMPO_VITA] = _segundos_para_hms(vita_seg)
    out[COL_TEMPO_ATENDIMENTO] = _segundos_para_hms(att_seg)
    return out


def _carregar_logs_por_atendimento(
    cursor,
    ids_atendimento: list[int] | set[int],
    *,
    tipo_campo: str,
) -> dict[int, list[dict[str, Any]]]:
    ids = sorted({int(i) for i in (ids_atendimento or []) if i is not None and int(i) > 0})
    if not ids:
        return {}
    por_att: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for offset in range(0, len(ids), _CHUNK_IDS):
        chunk = ids[offset : offset + _CHUNK_IDS]
        placeholders = ", ".join(["%s"] * len(chunk))
        cursor.execute(
            f"""
            SELECT id_atendimentos_log, tipo_campo_log, valor_anterior_log, valor_novo_log,
                   alterado_em_log, id_log_atendimentos_status
            FROM atendimentos_status_log
            WHERE tipo_campo_log = %s
              AND id_atendimentos_log IN ({placeholders})
            ORDER BY id_atendimentos_log, alterado_em_log, id_log_atendimentos_status
            """,
            (tipo_campo, *chunk),
        )
        for row in cursor.fetchall() or []:
            id_att = row.get("id_atendimentos_log")
            if id_att:
                por_att[int(id_att)].append(dict(row))
    por_att = _mesclar_historico_em_logs(cursor, dict(por_att), ids, tipo_campo=tipo_campo)
    return por_att


def carregar_logs_substatus_map(
    cursor, ids_atendimento: list[int] | set[int]
) -> dict[int, list[dict[str, Any]]]:
    return _carregar_logs_por_atendimento(cursor, ids_atendimento, tipo_campo="substatus")


def carregar_logs_status_map(
    cursor, ids_atendimento: list[int] | set[int]
) -> dict[int, list[dict[str, Any]]]:
    return _carregar_logs_por_atendimento(cursor, ids_atendimento, tipo_campo="status")


def carregar_motivos_map(
    cursor, ids_atendimento: list[int] | set[int]
) -> dict[int, str]:
    ids = sorted({int(i) for i in (ids_atendimento or []) if i is not None and int(i) > 0})
    if not ids:
        return {}
    out: dict[int, str] = {}
    for offset in range(0, len(ids), _CHUNK_IDS):
        chunk = ids[offset : offset + _CHUNK_IDS]
        placeholders = ", ".join(["%s"] * len(chunk))
        cursor.execute(
            f"""
            SELECT af.id_atendimento,
                   GROUP_CONCAT(m.descricao ORDER BY m.categoria, m.descricao SEPARATOR '; ') AS motivos
            FROM atendimentos_fora_padrao af
            JOIN motivos_fora_padrao m ON af.id_motivo = m.id
            WHERE af.id_atendimento IN ({placeholders})
            GROUP BY af.id_atendimento
            """,
            tuple(chunk),
        )
        for row in cursor.fetchall() or []:
            id_att = row.get("id_atendimento")
            if id_att:
                out[int(id_att)] = (row.get("motivos") or "").strip()
    return out


def metricas_map_por_atendimento(
    logs_por_att: dict[int, list[dict[str, Any]]],
    tz_sp=None,
    *,
    status_logs_por_att: dict[int, list[dict[str, Any]]] | None = None,
    metas_por_att: dict[int, Mapping[str, Any]] | None = None,
) -> dict[int, dict[str, str]]:
    tz = tz_sp or TZ_SP
    status_logs_por_att = status_logs_por_att or {}
    metas_por_att = metas_por_att or {}
    out: dict[int, dict[str, str]] = {}
    for id_att, logs in (logs_por_att or {}).items():
        meta = metas_por_att.get(id_att) or {}
        fim = inferir_fim_corte_atendimento(
            status_logs=status_logs_por_att.get(id_att),
            data_atendimento=meta.get("data_atendimentos") or meta.get("data_atendimento"),
            horario_finalizacao=meta.get("horario_finalizacao_atendimentos")
            or meta.get("horario_finalizacao")
            or meta.get("horario_final"),
            status_atendimento=meta.get("status_atendimentos") or meta.get("status"),
            tz_sp=tz,
        )
        out[id_att] = metricas_atendimento_logs(logs, tz, fim_corte=fim)
    return out
