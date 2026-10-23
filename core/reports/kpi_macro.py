"""KPIs macro FUST e PRODESP — visão operacional sem recorte por contratada."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ._fallback_tempo_em_andamento import fallback_preencher_tempo_em_andamento

SUB_AGUARDA_GESTAO = "Aguarda Gestão"
SUB_AGUARDANDO_CLIENTE = "Aguardando Cliente"
SUB_AGUARDA_CONTRATADA = "Aguarda Contratada"
SUB_FILA_REMOTA = "Aguardando Config. Remota"
SUB_EM_CADERNO = "Em Caderno de Teste"
SUB_LEGACY_TRIAGEM = "Aguardando Triagem"


def _txt(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def row_somente_agendado(row: Mapping[str, Any]) -> bool:
    id_att = row.get("id_atendimento") or row.get("id_atendimentos")
    if id_att is None or id_att == "":
        return True
    try:
        import pandas as pd

        if pd.isna(id_att):
            return True
    except (TypeError, ValueError, ImportError):
        pass
    return False


def segundos_hhmmss(segundos: float) -> str:
    total = max(0, int(segundos))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@dataclass
class KpiMacro:
    total: int = 0
    agendados: int = 0
    com_atividade: int = 0
    em_atendimento: int = 0
    aguarda_gestao: int = 0
    aguardando_cliente: int = 0
    aguarda_contratada: int = 0
    aguardando_remota: int = 0
    em_caderno: int = 0
    aguarda_licenca: int = 0
    parcial: int = 0
    concluidos: int = 0
    quebra: int = 0
    quebra_tbra: int = 0
    pct_concluidos: int = 0
    tempo_medio: str = "00:00:00"
    em_config_remota_cnt: int = 0
    aguardando_caderno_cnt: int = 0
    em_caderno_painel_cnt: int = 0
    aguardando_config_mpls_cnt: int = 0
    em_config_mpls_cnt: int = 0
    extras: dict[str, int] = field(default_factory=dict)

    @property
    def vazio(self) -> bool:
        return self.total <= 0


def _status(row: Mapping[str, Any]) -> str:
    return _txt(row, "status_atendimentos", "status")


def _sub(row: Mapping[str, Any]) -> str:
    return _txt(row, "substatus_atendimentos", "substatus")


def _analista(row: Mapping[str, Any]) -> str:
    return _txt(
        row,
        "analista_configuracao_atendimentos",
        "analista_atuante_atendimentos",
        "analista_atuante",
        "analista_configuracao",
    )


def _analista_implantacao(row: Mapping[str, Any]) -> str | None:
    """Extrai o nome do analista SOMENTE se for de implantação.

    Considera de implantação quando o nome vem de campos de configuração/atuação
    do atendimento direto (analista_configuracao_* ou analista_configuracao ou
    nome_analista). Retorna None quando o nome só viria de gestor
    (analista_atuante_atendimentos / analista_atuante) — ou seja, pessoa de
    gestão que acompanhou/validou mas não "pegou" o ticket de implantação.
    """
    impl = _txt(
        row,
        "nome_analista",
        "analista_configuracao_atendimentos",
        "analista_configuracao",
    )
    if impl:
        return impl
    # Fallback: se só existir analista_atuante_* e não for o mesmo nome de
    # analista_configuracao, considera gestor → retorna None.
    return None


_STATUS_CONCLUIDO_FUST = {"Concluido"}
_STATUS_CONCLUIDO_PRODESP = {"Concluído"}
_STATUS_PARCIAL = {"Concluído Parcial", "Concluida - entrega parcial"}
_STATUS_QUEBRA = {"Quebra", "Quebra TBRA"}


@dataclass
class TopAnalista:
    nome: str
    concluidos: int = 0
    quebra: int = 0
    parcial: int = 0
    fust: int = 0
    prodesp: int = 0

    @property
    def total(self) -> int:
        return self.concluidos + self.quebra + self.parcial


def _classificar_status(row: Mapping[str, Any], *, projeto: str) -> tuple[str, str, str]:
    status = _status(row)
    sub = _sub(row)
    concluidos = _STATUS_CONCLUIDO_PRODESP if projeto == "PRODESP" else _STATUS_CONCLUIDO_FUST
    concluido = status in concluidos and (projeto != "PRODESP" or sub == "Concluído")
    if status in _STATUS_QUEBRA:
        return "quebra", status, sub
    if status in _STATUS_PARCIAL:
        return "parcial", status, sub
    if concluido:
        return "concluidos", status, sub
    return "outro", status, sub


def _iterar_participacao(rows: Sequence[Mapping[str, Any]], *, projeto: str):
    for raw in rows or []:
        nome = _analista_implantacao(raw)
        if not nome:
            continue
        if row_somente_agendado(raw):
            continue
        categoria, _s, _ss = _classificar_status(raw, projeto=projeto)
        yield nome, categoria


def _agregar_top_projeto(rows: Sequence[Mapping[str, Any]], *, projeto: str, top: int) -> list[TopAnalista]:
    buckets: dict[str, TopAnalista] = {}
    for nome, cat in _iterar_participacao(list(rows or []), projeto=projeto):
        if nome not in buckets:
            buckets[nome] = TopAnalista(nome=nome)
        a = buckets[nome]
        if cat == "concluidos":
            a.concluidos += 1
        elif cat == "quebra":
            a.quebra += 1
        elif cat == "parcial":
            a.parcial += 1
        if projeto == "FUST":
            a.fust += 1
        elif projeto == "PRODESP":
            a.prodesp += 1
    items = list(buckets.values())
    items.sort(key=lambda a: (-a.total, -(a.fust + a.prodesp), a.nome))
    return items[: max(1, int(top))]


def agregar_top5_por_projeto(
    rows_fust: Sequence[Mapping[str, Any]] | None = None,
    rows_prodesp: Sequence[Mapping[str, Any]] | None = None,
    *,
    top: int = 5,
) -> tuple[list[TopAnalista], list[TopAnalista], list[TopAnalista]]:
    """TOP 5 analistas por projeto (FUST / PRODESP) e GERAL (soma de ambos os projetos).

    Cada projeto é calculado ISOLADAMENTE: top_fust usa apenas rows_fust;
    top_prodesp usa apenas rows_prodesp. Apenas o GERAL combina os dois.
    Analistas de gestão (cujo nome só existe em campos atuante_*, sem
    analista_configuracao_* ou nome_analista) são EXCLUÍDOS do ranking.
    """
    top_fust = _agregar_top_projeto(rows_fust or [], projeto="FUST", top=top)
    top_prodesp = _agregar_top_projeto(rows_prodesp or [], projeto="PRODESP", top=top)

    buckets_geral: dict[str, TopAnalista] = {}
    for fonte, proj_nome in (
        (top_fust, "FUST"),
        (top_prodesp, "PRODESP"),
    ):
        for a in fonte:
            nome = a.nome
            if nome not in buckets_geral:
                buckets_geral[nome] = TopAnalista(nome=nome)
            g = buckets_geral[nome]
            g.concluidos += int(a.concluidos)
            g.quebra += int(a.quebra)
            g.parcial += int(a.parcial)
            if proj_nome == "FUST":
                g.fust += int(a.fust) or int(a.total)
            else:
                g.prodesp += int(a.prodesp) or int(a.total)
    geral = list(buckets_geral.values())
    geral.sort(key=lambda a: (-a.total, -(a.fust + a.prodesp), a.nome))
    top_geral = geral[: max(1, int(top))]
    return top_fust, top_prodesp, top_geral


@dataclass
class AtendimentoAtivoSupervisao:
    projeto: str
    chave: str
    unidade: str
    status: str
    substatus: str
    tempo_atuacao_seg: int
    analista: str

    @property
    def tempo_atuacao_label(self) -> str:
        return segundos_hhmmss(self.tempo_atuacao_seg)


def listar_atendimentos_ativos(
    rows_fust: Sequence[Mapping[str, Any]] | None = None,
    rows_prodesp: Sequence[Mapping[str, Any]] | None = None,
    *,
    agora=None,
) -> list[AtendimentoAtivoSupervisao]:
    """Atendimentos em andamento (Em Atendimento / qualquer etapa produtiva) ou ainda
    na fila aguardando analista. Ordem: maior tempo de atuação primeiro.
    """
    from datetime import datetime as _dt
    import pytz

    tz = pytz.timezone("America/Sao_Paulo")
    agora_tz = agora or _dt.now(tz)
    items: list[AtendimentoAtivoSupervisao] = []

    def _tempo(row: Mapping[str, Any]) -> int:
        hi = row.get("horario_inicio_atendimentos") or row.get("horario_inicio")
        if hi is None:
            return 0
        try:
            from datetime import timedelta as _td
            if isinstance(hi, _td):
                return max(0, int(hi.total_seconds()))
            s = str(hi)
            if len(s) >= 8:
                hh = int(s[0:2]); mm = int(s[3:5]); ss = int(s[6:8])
                return max(0, hh * 3600 + mm * 60 + ss)
        except (TypeError, ValueError, IndexError):
            pass
        return 0

    def _chave_unidade(row: Mapping[str, Any], *, projeto: str) -> tuple[str, str]:
        if projeto == "FUST":
            chave = str(row.get("inep_escolas") or row.get("inep") or "")
            unidade = str(row.get("nome_escolas") or row.get("nome_unidades") or "")
        else:
            acr = str(row.get("acronimo_unidades") or "").strip()
            nome = str(row.get("nome_unidades") or "").strip()
            chave = str(row.get("id_vgr_unidades") or "")
            unidade = f"{acr} — {nome}" if acr and nome else (acr or nome)
        return chave, unidade

    for projeto, rows in (("FUST", list(rows_fust or [])), ("PRODESP", list(rows_prodesp or []))):
        for r in rows:
            status = _status(r) or ""
            sub = _sub(r) or ""
            if status.strip().lower() == "agendado":
                continue
            etapa = status + " " + sub
            em_andamento = (
                status in {"Em Atendimento", "Em atuacao tecnica", "Em atuação técnica", "Em Andamento"}
                or "Em " in etapa or "Aguardando " in etapa or "Aguarda " in etapa
            )
            if not em_andamento:
                continue
            chave, unidade = _chave_unidade(r, projeto=projeto)
            if not chave and not unidade:
                continue
            analista = _analista(r) or "—"
            items.append(
                AtendimentoAtivoSupervisao(
                    projeto=projeto,
                    chave=chave,
                    unidade=unidade,
                    status=status or "—",
                    substatus=sub or "—",
                    tempo_atuacao_seg=_tempo(r),
                    analista=analista,
                )
            )
    items.sort(key=lambda a: (-a.tempo_atuacao_seg, a.projeto, a.chave))
    return items


def calcular_kpis_prodesp(
    rows: list[Mapping[str, Any]],
    resumo_kpi: Mapping[str, Any] | None = None,
) -> KpiMacro:
    """Espelha o dashboard PRODESP KPI TEMPO MÉDIO do frontend script_gestao_atendimentos_prodesp.js L794-L795:
    tempo_em_segundos != null (inclusive 0) entra, média = sum/length.
    Atendimentos EM ANDAMENTO sem horario_final ficam NULL no dashboard e portanto NÃO entram.
    """
    kpi = KpiMacro()
    tempos: list[int] = []
    for row in rows:
        if row_somente_agendado(row):
            kpi.agendados += 1
            continue
        kpi.com_atividade += 1
        status = _status(row)
        sub = _sub(row)
        concluido = status == "Concluído" and sub == "Concluído"
        if status == "Em Atendimento":
            kpi.em_atendimento += 1
            if sub == SUB_AGUARDANDO_CLIENTE:
                kpi.aguardando_cliente += 1
            elif sub in (SUB_AGUARDA_GESTAO, SUB_LEGACY_TRIAGEM):
                kpi.aguarda_gestao += 1
            elif "Aguarda Contratada" in sub or sub == "Aguardando retorno field":
                kpi.aguarda_contratada += 1
            elif sub == "Aguarda Licença":
                kpi.aguarda_licenca += 1
            elif sub == SUB_FILA_REMOTA:
                kpi.aguardando_remota += 1
        elif status in ("Concluído Parcial", "Concluida - entrega parcial"):
            kpi.parcial += 1
        elif concluido:
            kpi.concluidos += 1
        elif status == "Quebra":
            kpi.quebra += 1
        elif status == "Quebra TBRA":
            kpi.quebra_tbra += 1
        seg = row.get("tempo_em_segundos")
        if seg is not None:
            try:
                v = int(seg) if not isinstance(seg, int) else seg
                tempos.append(v)
            except (TypeError, ValueError):
                pass
    kpi.total = kpi.agendados + kpi.com_atividade
    if kpi.total > 0:
        kpi.pct_concluidos = int(round((kpi.concluidos / kpi.total) * 100))
    if tempos:
        kpi.tempo_medio = segundos_hhmmss(sum(tempos) / len(tempos))
    if resumo_kpi:
        try:
            kpi.em_config_remota_cnt = int(resumo_kpi.get("em_config_remota_cnt") or 0)
        except (TypeError, ValueError):
            kpi.em_config_remota_cnt = 0
        try:
            kpi.aguardando_caderno_cnt = int(resumo_kpi.get("aguardando_caderno_cnt") or 0)
        except (TypeError, ValueError):
            kpi.aguardando_caderno_cnt = 0
        try:
            kpi.em_caderno_painel_cnt = int(resumo_kpi.get("em_caderno_cnt") or 0)
        except (TypeError, ValueError):
            kpi.em_caderno_painel_cnt = 0
        try:
            kpi.aguardando_config_mpls_cnt = int(resumo_kpi.get("aguardando_config_mpls_cnt") or 0)
        except (TypeError, ValueError):
            kpi.aguardando_config_mpls_cnt = 0
        try:
            kpi.em_config_mpls_cnt = int(resumo_kpi.get("em_config_mpls_cnt") or 0)
        except (TypeError, ValueError):
            kpi.em_config_mpls_cnt = 0
    return kpi


def calcular_kpis_fust(
    rows: list[Mapping[str, Any]],
    resumo_kpi: Mapping[str, Any] | None = None,
) -> KpiMacro:
    """Espelha o dashboard FUST KPI TEMPO MÉDIO script_fust_dashboard_kpis.js L872:
    if (row.tempo_em_segundos != null) seconds.push(Number(row.tempo_em_segundos) || 0);
    média = sum/len.
    Atendimentos SEM tempo_em_segundos (NULL, em andamento) são EXCLUÍDOS do array.
    """
    kpi = KpiMacro()
    tempos: list[int] = []
    for row in rows:
        if row_somente_agendado(row) or _status(row) == "Agendado":
            kpi.agendados += 1
            continue
        kpi.com_atividade += 1
        status = _status(row)
        sub = _sub(row)
        concluido = status == "Concluido"
        if status in ("Em Atendimento", "Em atuacao tecnica", "Em atuação técnica"):
            kpi.em_atendimento += 1
        if sub == SUB_AGUARDA_GESTAO:
            kpi.aguarda_gestao += 1
        elif sub == SUB_AGUARDANDO_CLIENTE:
            kpi.aguardando_cliente += 1
        elif sub == SUB_AGUARDA_CONTRATADA:
            kpi.aguarda_contratada += 1
        elif sub == SUB_FILA_REMOTA:
            kpi.aguardando_remota += 1
        elif sub == SUB_EM_CADERNO:
            kpi.em_caderno += 1
        if status == "Quebra":
            kpi.quebra += 1
        elif status == "Concluida - entrega parcial":
            kpi.parcial += 1
        elif concluido:
            kpi.concluidos += 1
        seg = row.get("tempo_em_segundos")
        if seg is None:
            seg = row.get("tempo_total_parada_segundos")
        if seg is not None:
            try:
                v = int(seg) if not isinstance(seg, int) else seg
                if v < 0:
                    v = 0
                tempos.append(v)
            except (TypeError, ValueError):
                tempos.append(0)
    kpi.total = kpi.agendados + kpi.com_atividade
    if kpi.total > 0:
        kpi.pct_concluidos = int(round((kpi.concluidos / kpi.total) * 100))
    if tempos:
        kpi.tempo_medio = segundos_hhmmss(sum(tempos) / len(tempos))
    if resumo_kpi:
        try:
            kpi.em_config_remota_cnt = int(resumo_kpi.get("em_config_remota_cnt") or 0)
        except (TypeError, ValueError):
            kpi.em_config_remota_cnt = 0
        try:
            kpi.aguardando_caderno_cnt = int(resumo_kpi.get("aguardando_caderno_cnt") or 0)
        except (TypeError, ValueError):
            kpi.aguardando_caderno_cnt = 0
        try:
            kpi.em_caderno_painel_cnt = int(resumo_kpi.get("em_caderno_cnt") or 0)
        except (TypeError, ValueError):
            kpi.em_caderno_painel_cnt = 0
        try:
            kpi.aguardando_config_mpls_cnt = int(resumo_kpi.get("aguardando_config_mpls_cnt") or 0)
        except (TypeError, ValueError):
            kpi.aguardando_config_mpls_cnt = 0
        try:
            kpi.em_config_mpls_cnt = int(resumo_kpi.get("em_config_mpls_cnt") or 0)
        except (TypeError, ValueError):
            kpi.em_config_mpls_cnt = 0
    return kpi


def spec_cards_prodesp(kpi: KpiMacro) -> list[tuple[str, str, str, str]]:
    hint_total = f"{kpi.agendados} agend. + {kpi.com_atividade} ativos"
    return [
        ("Total período", str(kpi.total), hint_total, "#6b2d8a"),
        ("Agendados", str(kpi.agendados), "Sem ativ.", "#6c757d"),
        ("Em atendimento", str(kpi.em_atendimento), "", "#0d6efd"),
        ("Aguarda Gestão", str(kpi.aguarda_gestao), "Substatus", "#6c757d"),
        ("Aguard. cliente", str(kpi.aguardando_cliente), "Substatus", "#fd7e14"),
        ("Aguarda Contratada", str(kpi.aguarda_contratada), "Substatus", "#e67e22"),
        ("Aguarda Licença", str(kpi.aguarda_licenca), "Substatus", "#e67e22"),
        ("Aguard. Config.", str(kpi.aguardando_remota), "Fila remota", "#0dcaf0"),
        ("Em Config Remota", str(kpi.em_config_remota_cnt), "3 substatus (painel)", "#16a34a"),
        ("Agu.Conf.MPLS", str(kpi.aguardando_config_mpls_cnt), "Fila MPLS", "#0891b2"),
        ("Conf.MPLS", str(kpi.em_config_mpls_cnt), "Etapa MPLS (painel)", "#15803d"),
        ("Aguard. Caderno", str(kpi.aguardando_caderno_cnt), "Fila caderno (painel)", "#0284c7"),
        ("Em Caderno", str(kpi.em_caderno_painel_cnt), "Etapa caderno (painel)", "#0d6efd"),
        ("Quebra", str(kpi.quebra), "", "#dc3545"),
        ("Quebra TBRA", str(kpi.quebra_tbra), "", "#b02a37"),
        ("Parcial", str(kpi.parcial), "", "#0dcaf0"),
        ("Migrados", str(kpi.concluidos), "Status Concluído", "#198754"),
        ("% migrados", f"{kpi.pct_concluidos}%", f"{kpi.concluidos} ÷ {kpi.total or 0}", "#198754"),
        ("Tempo médio", kpi.tempo_medio, "Média (todos c/ ativ.)", "#6b2d8a"),
    ]


def spec_cards_fust(kpi: KpiMacro) -> list[tuple[str, str, str, str]]:
    hint_total = f"{kpi.agendados} agend. + {kpi.com_atividade} ativos"
    return [
        ("Total período", str(kpi.total), hint_total, "#5a2e7c"),
        ("Agendados", str(kpi.agendados), "Sem ativ.", "#6c757d"),
        ("Em atendimento", str(kpi.em_atendimento), "", "#0d6efd"),
        ("Aguarda Gestão", str(kpi.aguarda_gestao), "Substatus", "#6c757d"),
        ("Aguard. cliente", str(kpi.aguardando_cliente), "Substatus", "#fd7e14"),
        ("Aguarda Contratada", str(kpi.aguarda_contratada), "Substatus", "#e67e22"),
        ("Aguard. Config.", str(kpi.aguardando_remota), "Fila remota", "#0dcaf0"),
        ("Em Config Remota", str(kpi.em_config_remota_cnt), "3 substatus (painel)", "#16a34a"),
        ("Aguard. Caderno", str(kpi.aguardando_caderno_cnt), "Fila caderno (painel)", "#0284c7"),
        ("Em Caderno", str(kpi.em_caderno_painel_cnt), "Etapa caderno (painel)", "#0d6efd"),
        ("Quebra", str(kpi.quebra), "", "#dc3545"),
        ("Parcial", str(kpi.parcial), "", "#0dcaf0"),
        ("Concluídos", str(kpi.concluidos), "Status Concluido", "#198754"),
        ("% concluídos", f"{kpi.pct_concluidos}%", f"{kpi.concluidos} ÷ {kpi.total or 0}", "#198754"),
        ("Tempo médio", kpi.tempo_medio, "Média (todos c/ ativ.)", "#5a2e7c"),
    ]
