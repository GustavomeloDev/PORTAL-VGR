"""Regras puras da Gestão de Atendimentos VGR (sem acesso a banco).

Espelha a semântica do dashboard PRODESP
(``script_gestao_atendimentos_prodesp.js`` + ``dashboard_escopo``):

- **Total no período** = agendados (sem atividade iniciada) + com atividade.
- **Agendado no período**: agenda ativa com ``data_agendamento`` no filtro.
- **Com atividade**: atendimento ativo cuja atividade (abertura, ou criação
  quando ainda não aberto) caiu no filtro, OU cuja agenda caiu no filtro.
- **Fora de escopo**: com atividade no período, mas agenda em outra data
  (ou walk-in sem agenda).

Particularidades VGR (catálogo próprio — ``catalogo_atendimento``):
- Atendimento com status ``Agendado`` (fase de preparação: Check-list etc.)
  conta como *Agendado* (sem atividade iniciada), igual à linha sem atendimento.
- Agenda publicada («Agendado») com atendimento ainda NÃO iniciado também é
  *Agendado* — mesma regra da fila (``vgrRowIsAgendado``), para os cards e a
  tabela mostrarem o mesmo número.
- Agenda ``Improdutiva`` sem atendimento é uma quebra de agenda: fica FORA do
  total (informada à parte no hint e no relatório).
- Concluídos = status «Concluído» + substatus «Concluído» (Day After à parte).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from vgr.vgr.operacao.catalogo_atendimento import (
    STATUS_AGENDADO,
    STATUS_OPERACIONAL,
    is_status_agendado,
    is_status_final,
)

# Janela máxima aceita pelo filtro (evita relatório/consulta gigantes por engano).
PERIODO_MAX_DIAS = 366

STATUS_AGENDA_IMPRODUTIVA = "Improdutiva"

SUB_AGUARDA_CLIENTE = "Aguarda Cliente"
SUB_AGUARDA_CONTRATADA = "Aguarda Contratada"
SUB_AGUARDA_GESTAO = "Aguarda Gestão"

# Etapas técnicas do fluxo «Em Atendimento» (filas de configuração).
SUBSTATUS_FLUXO_TECNICO: frozenset[str] = frozenset(
    {
        "Aguardando Config. Remota",
        "Em Configuração Remota",
        "Aguardando Config. MPLS",
        "Em Configuração do MPLS",
        "Aguardando Caderno de Teste",
        "Em Caderno de Teste",
    }
)

# Substatus sintético da fila VGR para agenda publicada sem atividade iniciada.
SUBSTATUS_SEM_ATENDIMENTO = "Sem atendimento Iniciado"

CATEGORIA_AGENDADO = "agendado"
CATEGORIA_ATIVIDADE = "atividade"
CATEGORIA_IMPRODUTIVA = "improdutiva"

ESCOPO_AGENDADO_PENDENTE = "Agendado pendente"
ESCOPO_AGENDADO_NO_PERIODO = "Agendado no período"
ESCOPO_FORA_DE_ESCOPO = "Fora de escopo"
ESCOPO_IMPRODUTIVA = "Agenda improdutiva"


# ---------------------------------------------------------------------------
# Datas / período
# ---------------------------------------------------------------------------
def to_date(value: Any) -> date | None:
    """Aceita date, datetime ou string ISO (YYYY-MM-DD[ HH:MM:SS])."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def to_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    s = str(value).strip().replace("T", " ")
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19])
    except ValueError:
        return None


def parse_periodo(
    start_raw: str | None,
    end_raw: str | None,
    *,
    hoje: date,
) -> tuple[date, date]:
    """Valida o período do filtro (padrão: hoje/hoje).

    Levanta ValueError com mensagem pronta para a UI.
    """
    start_s = (start_raw or "").strip()
    end_s = (end_raw or "").strip()
    try:
        start = date.fromisoformat(start_s) if start_s else hoje
        end = date.fromisoformat(end_s) if end_s else start
    except ValueError as exc:
        raise ValueError("Data inválida. Use o formato AAAA-MM-DD.") from exc
    if start > end:
        raise ValueError("Data Início não pode ser maior que Data Fim.")
    if (end - start).days + 1 > PERIODO_MAX_DIAS:
        raise ValueError(f"Período máximo de {PERIODO_MAX_DIAS} dias.")
    return start, end


def dia_no_periodo(d: Any, start: date, end: date) -> bool:
    dd = to_date(d)
    return dd is not None and start <= dd <= end


def fmt_hhmmss(total_seconds: float | int | None) -> str:
    if total_seconds is None:
        return "00:00:00"
    try:
        total = int(round(float(total_seconds)))
    except (TypeError, ValueError):
        return "00:00:00"
    total = max(total, 0)
    hh, rem = divmod(total, 3600)
    mm, ss = divmod(rem, 60)
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


# ---------------------------------------------------------------------------
# Linhas do período
# ---------------------------------------------------------------------------
def chave_linha(row: dict[str, Any]) -> tuple[str, int]:
    """Uma linha por atendimento; agenda sem atendimento usa o id da agenda."""
    id_at = row.get("id_atendimento")
    if id_at not in (None, ""):
        return ("at", int(id_at))
    return ("ag", int(row.get("id_agendamento") or 0))


def mesclar_linhas(*grupos: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une linhas de agenda + atividade sem duplicar (primeira ocorrência vence)."""
    vistos: set[tuple[str, int]] = set()
    out: list[dict[str, Any]] = []
    for grupo in grupos:
        for row in grupo or []:
            k = chave_linha(row)
            if k in vistos:
                continue
            vistos.add(k)
            out.append(row)
    return out


def _sem_atendimento(row: dict[str, Any]) -> bool:
    return row.get("id_atendimento") in (None, "")


def categoria_linha(row: dict[str, Any]) -> str:
    """Mesma regra da fila VGR (``vgrRowIsAgendado`` em vgr_atendimentos.js).

    - sem atendimento: agenda (ou improdutiva, que fica fora do total);
    - atendimento com status «Agendado» (Check-list etc.): agendado;
    - agenda publicada («Agendado») cujo atendimento ainda não iniciou
      (``atendimento_iniciado`` = 0, ex.: criado por confirmar_agendado
      em Aguarda Gestão): agendado — «Sem atendimento Iniciado»;
    - demais: com atividade.
    """
    status_ag = (row.get("status_agendamento") or "").strip()
    if _sem_atendimento(row):
        if status_ag == STATUS_AGENDA_IMPRODUTIVA:
            return CATEGORIA_IMPRODUTIVA
        return CATEGORIA_AGENDADO
    status = row.get("status_atendimento")
    if is_status_final(status):
        # Final sempre conta como atividade (o repo marca iniciado ao finalizar;
        # o guard protege registros legados com atendimento_iniciado = 0).
        return CATEGORIA_ATIVIDADE
    if is_status_agendado(status):
        return CATEGORIA_AGENDADO
    if status_ag == STATUS_AGENDADO and int(row.get("atendimento_iniciado") or 0) != 1:
        return CATEGORIA_AGENDADO
    return CATEGORIA_ATIVIDADE


def grupos_linha(row: dict[str, Any]) -> list[str]:
    """Chaves de KPI em que a linha conta (fonte única para cards e filtros).

    Ex.: Em Atendimento/Aguarda Cliente → ["com_atividade", "em_atendimento",
    "aguarda_cliente"]. Improdutiva → [] (fora do total).
    """
    cat = categoria_linha(row)
    if cat == CATEGORIA_IMPRODUTIVA:
        return []
    if cat == CATEGORIA_AGENDADO:
        return ["agendados"]

    grupos = ["com_atividade"]
    status = (row.get("status_atendimento") or "").strip()
    sub = (row.get("substatus_atendimento") or "").strip()
    if status == STATUS_OPERACIONAL:
        grupos.append("em_atendimento")
        if sub == SUB_AGUARDA_CLIENTE:
            grupos.append("aguarda_cliente")
        elif sub == SUB_AGUARDA_CONTRATADA:
            grupos.append("aguarda_contratada")
        elif sub == SUB_AGUARDA_GESTAO:
            grupos.append("aguarda_gestao")
        elif sub in SUBSTATUS_FLUXO_TECNICO:
            grupos.append("fluxo_tecnico")
    elif status == "Concluído Parcial":
        grupos.append("concluido_parcial")
    elif status == "Concluído" and sub == "Concluído":
        grupos.append("concluidos")
    elif status == "Concluído" and sub == "Day After":
        grupos.append("day_after")
    elif status == "Quebra":
        grupos.append("quebra")
    else:
        grupos.append("outros_status")
    return grupos


def escopo_linha(row: dict[str, Any], start: date, end: date) -> str:
    cat = categoria_linha(row)
    if cat == CATEGORIA_IMPRODUTIVA:
        return ESCOPO_IMPRODUTIVA
    if cat == CATEGORIA_AGENDADO:
        return ESCOPO_AGENDADO_PENDENTE
    if dia_no_periodo(row.get("data_agendamento"), start, end):
        return ESCOPO_AGENDADO_NO_PERIODO
    return ESCOPO_FORA_DE_ESCOPO


def status_exibicao(row: dict[str, Any]) -> tuple[str, str]:
    """(status, substatus) exibidos na tabela/relatório — padrão da fila VGR."""
    status = (row.get("status_atendimento") or "").strip()
    sub = (row.get("substatus_atendimento") or "").strip()
    if categoria_linha(row) == CATEGORIA_AGENDADO and status != STATUS_AGENDADO:
        return STATUS_AGENDADO, SUBSTATUS_SEM_ATENDIMENTO
    return status, sub


def tempo_atendimento_segundos(row: dict[str, Any]) -> int | None:
    """Duração abertura → fechamento (apenas atendimentos finalizados)."""
    if not is_status_final(row.get("status_atendimento")):
        return None
    ini = to_datetime(row.get("abertura"))
    fim = to_datetime(row.get("fechamento"))
    if not ini or not fim:
        return None
    seg = int((fim - ini).total_seconds())
    return seg if seg >= 0 else None


def _pct(parte: int, total: int) -> int:
    return round((parte / total) * 100) if total > 0 else 0


KPI_CONTADORES: tuple[str, ...] = (
    "agendados",
    "com_atividade",
    "em_atendimento",
    "aguarda_cliente",
    "aguarda_contratada",
    "aguarda_gestao",
    "fluxo_tecnico",
    "quebra",
    "concluido_parcial",
    "concluidos",
    "day_after",
    "outros_status",
)


def calcular_kpis(
    rows: Iterable[dict[str, Any]],
    start: date,
    end: date,
) -> dict[str, Any]:
    """KPIs macro do período (mesma anatomia dos cards PRODESP)."""
    k: dict[str, Any] = {chave: 0 for chave in KPI_CONTADORES}
    k.update(
        {
            "total": 0,
            "improdutivas": 0,
            "pct_concluidos": 0,
            "tempo_medio": "00:00:00",
            "tempo_medio_amostras": 0,
        }
    )
    det = {
        "agendados_pend": 0,
        "agendados_finalizados": 0,
        "agendados_ativos": 0,
        "fora_escopo_finalizados": 0,
        "fora_escopo_ativos": 0,
        "total": 0,
    }
    tempos: list[int] = []

    for row in rows or []:
        grupos = grupos_linha(row)
        if not grupos:
            k["improdutivas"] += 1
            continue
        for g in grupos:
            k[g] += 1
        if "agendados" in grupos:
            det["agendados_pend"] += 1
            continue

        ativo = "em_atendimento" in grupos
        if dia_no_periodo(row.get("data_agendamento"), start, end):
            det["agendados_ativos" if ativo else "agendados_finalizados"] += 1
        else:
            det["fora_escopo_ativos" if ativo else "fora_escopo_finalizados"] += 1

        seg = tempo_atendimento_segundos(row)
        if seg is not None:
            tempos.append(seg)

    k["total"] = k["agendados"] + k["com_atividade"]
    det["total"] = (
        det["agendados_pend"]
        + det["agendados_finalizados"]
        + det["agendados_ativos"]
        + det["fora_escopo_finalizados"]
        + det["fora_escopo_ativos"]
    )
    k["pct_concluidos"] = _pct(k["concluidos"], k["total"])
    if tempos:
        k["tempo_medio"] = fmt_hhmmss(sum(tempos) / len(tempos))
        k["tempo_medio_amostras"] = len(tempos)

    return {"kpis": k, "detalhe_total": det}


def linhas_tabela(
    rows: Iterable[dict[str, Any]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """Linhas da tabela de gestão (mesmo conjunto do «Total no período»).

    Cópias anotadas — não altera as linhas usadas no cálculo dos KPIs:
      - ``gestao_grupos``: chaves de KPI da linha (filtro dos cards);
      - ``gestao_escopo``: Agendado pendente / no período / Fora de escopo;
      - status/substatus de exibição (agenda sem início → «Agendado»).
    Agendas improdutivas ficam fora (estão no relatório).
    """
    out: list[dict[str, Any]] = []
    for row in rows or []:
        grupos = grupos_linha(row)
        if not grupos:
            continue
        r = dict(row)
        status, sub = status_exibicao(row)
        r["status_atendimento"] = status or None
        r["substatus_atendimento"] = sub or None
        r["gestao_grupos"] = grupos
        r["gestao_escopo"] = escopo_linha(row, start, end)
        out.append(r)
    return out


def hint_total_periodo(det: dict[str, Any], improdutivas: int = 0) -> str:
    """Texto do card «Total no período» (mesmo formato do PRODESP)."""
    txt = (
        f"{det.get('agendados_pend', 0)} Agendados Pend. + "
        f"{det.get('agendados_finalizados', 0)} Agendados Finalizados + "
        f"{det.get('agendados_ativos', 0)} Agendados Ativos + "
        f"{det.get('fora_escopo_finalizados', 0)} Fora Escopo Finalizado + "
        f"{det.get('fora_escopo_ativos', 0)} Fora Escopo Ativo"
    )
    if improdutivas:
        txt += f" · {improdutivas} improdutiva(s) fora do total"
    return txt


def resumo_periodo_payload(
    rows: list[dict[str, Any]],
    start: date,
    end: date,
) -> dict[str, Any]:
    """Payload completo da API de KPIs (sem linhas)."""
    calc = calcular_kpis(rows, start, end)
    calc["hint_total"] = hint_total_periodo(
        calc["detalhe_total"], calc["kpis"]["improdutivas"]
    )
    calc["periodo"] = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "dias": (end - start).days + 1,
    }
    return calc


__all__ = [
    "PERIODO_MAX_DIAS",
    "ESCOPO_AGENDADO_PENDENTE",
    "ESCOPO_AGENDADO_NO_PERIODO",
    "ESCOPO_FORA_DE_ESCOPO",
    "ESCOPO_IMPRODUTIVA",
    "calcular_kpis",
    "categoria_linha",
    "escopo_linha",
    "fmt_hhmmss",
    "grupos_linha",
    "linhas_tabela",
    "status_exibicao",
    "hint_total_periodo",
    "mesclar_linhas",
    "parse_periodo",
    "resumo_periodo_payload",
    "tempo_atendimento_segundos",
    "to_date",
    "to_datetime",
]
