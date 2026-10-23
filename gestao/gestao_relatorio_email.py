"""
Relatório executivo PRODESP — envio automático por e-mail (dashboard de gestão).
"""
from __future__ import annotations

import base64
import html
import io
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Mapping, Optional

TipoRelatorioGestao = Literal["periodico", "final"]
RelatorioVariant = Literal["gestao", "tbra"]

STATUS_ATENDIMENTO_ATIVO = frozenset({"Em Atendimento"})

import pandas as pd
import pytz

from prodesp.prodesp.blueprint.agendamento_csv_notifier import (
    build_email_assinatura_vita_html,
    send_graph_html_email,
)
from prodesp.prodesp.atendimento_business_rules import (
    SUBSTATUS_AGUARDA_GESTAO,
    SUBSTATUS_AGUARDA_LICENCA,
    SUBSTATUS_AGUARDANDO_CLIENTE,
    SUBSTATUS_LEGACY_TRIAGEM,
    is_substatus_aguarda_contratada,
)

logger = logging.getLogger(__name__)

TZ_SP = pytz.timezone("America/Sao_Paulo")

DEFAULT_GESTAO_RECIPIENTS = [
    "fabiana.cruz@telefonica.com",
    "celso.previato@telefonica.com",
    "sandra.psilva@telefonica.com",
    "vitoria.nnascimento@telefonica.com",
    "glaucia.lima@telefonica.com",
    "helio.nascimento@telefonica.com",
    "felipe.paixao@telefonica.com",
    "CAQ.vita.br@telefonica.com",
]

from prodesp.prodesp.gestao.relatorio_observacoes import (
    carregar_observacoes_map as _carregar_observacoes_map,
    carregar_substatus_historico_map as _carregar_substatus_historico_map,
    date_range_exclusive,
    observacoes_linha_relatorio as _observacoes_linha,
)
from prodesp.prodesp.gestao.relatorio_tempos import (
    COL_TEMPO_ATENDIMENTO,
    COL_TEMPO_VITA,
    carregar_logs_substatus_map,
    carregar_logs_status_map,
    carregar_motivos_map,
    colunas_tempo_etapa,
    metricas_map_por_atendimento,
)

RELATORIO_COLUNAS_BASE = [
    "ID VGR",
    "Data Agendamento",
    "Hora Agendamento",
    "Data Atendimento",
    "Status",
    "Substatus",
    "Motivo",
    "Contratada",
    "Início da Atividade",
    "Horário Finalização",
    "Observações",
    "Nome Unidade",
    "Endereço",
    "Cidade",
    "UF",
]

RELATORIO_COLUNAS_TBRA = [
    c for c in RELATORIO_COLUNAS_BASE
    if c not in ("Início da Atividade", "Horário Finalização")
]

RELATORIO_COLUNAS = [
    *RELATORIO_COLUNAS_BASE[:11],
    "Tck NOC",
    *RELATORIO_COLUNAS_BASE[11:],
    COL_TEMPO_VITA,
    COL_TEMPO_ATENDIMENTO,
    *colunas_tempo_etapa(),
]


def colunas_relatorio(variant: RelatorioVariant = "gestao") -> list[str]:
    return RELATORIO_COLUNAS_TBRA if variant == "tbra" else RELATORIO_COLUNAS


@dataclass
class GestaoKpiResumo:
    total: int = 0
    agendados: int = 0
    com_atividade: int = 0
    em_atendimento: int = 0
    aguardando_cliente: int = 0
    aguarda_gestao: int = 0
    aguarda_contratada: int = 0
    aguarda_licenca: int = 0
    parcial: int = 0
    migrados: int = 0
    quebra: int = 0
    quebra_tbra: int = 0
    pct_migrados: int = 0
    tempo_medio: str = "00:00:00"


@dataclass(frozen=True)
class ResultadoEnvioRelatorioGestao:
    enviado: bool = False
    omitido_sem_conteudo: bool = False
    omitido_dia_encerrado: bool = False
    omitido_igual: bool = False

    @property
    def slot_concluido(self) -> bool:
        """Envio ok ou omissão intencional — slot não deve reprocessar."""
        return (
            self.enviado
            or self.omitido_sem_conteudo
            or self.omitido_dia_encerrado
            or self.omitido_igual
        )

    def como_resultado(self):
        """Converte para o resultado genérico do agendador (core.reports.report_settings)."""
        from core.reports.report_settings import ENVIADO, omitido

        if self.enviado:
            return ENVIADO
        if self.omitido_sem_conteudo:
            return omitido("sem_dados")
        if self.omitido_dia_encerrado:
            return omitido("encerrado")
        if self.omitido_igual:
            return omitido("igual")
        return omitido("falha")

    @classmethod
    def sucesso(cls) -> ResultadoEnvioRelatorioGestao:
        return cls(enviado=True)

    @classmethod
    def omitido(cls) -> ResultadoEnvioRelatorioGestao:
        return cls(omitido_sem_conteudo=True)

    @classmethod
    def omitido_encerrado(cls) -> ResultadoEnvioRelatorioGestao:
        """Periódico omitido: dia já elegível a Report Final (sem atendimento em aberto)."""
        return cls(omitido_dia_encerrado=True)

    @classmethod
    def falha(cls) -> ResultadoEnvioRelatorioGestao:
        return cls()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "sim", "on")


def recipients_gestao_from_env() -> list[str]:
    raw = (os.getenv("PRODESP_GESTAO_RELATORIO_EMAIL_TO") or "").strip()
    if raw:
        return [e.strip() for e in raw.replace(",", ";").split(";") if e.strip()]
    return list(DEFAULT_GESTAO_RECIPIENTS)


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


def contratada_row_key(row: Mapping[str, Any]) -> str:
    """Mesma regra de prodespContratadaRowKey (dashboard gestão)."""
    if row_somente_agendado(row):
        planejada = (
            row.get("contratada_planejada_unidades")
            or row.get("contratada_atendimentos")
            or ""
        )
        planejada = str(planejada).strip()
        return planejada or "Não Informado"
    efetiva = str(row.get("contratada_atendimentos") or "").strip()
    if efetiva:
        return efetiva
    planejada = str(row.get("contratada_planejada_unidades") or "").strip()
    return planejada or "Não Informado"


def calc_pct_migrados_gestao(migrados: int, total: int) -> int:
    """
    % Migrados do card taxa-sucesso-valor (dashboard + e-mail):
    concluídos (status Concluído + substatus Concluído)
    ÷ total no período (agendados sem atividade + atendimentos com atividade iniciada).
    """
    if total <= 0:
        return 0
    return int(round((migrados / total) * 100))


def _format_data_br(val: Any) -> str:
    if val is None or val == "":
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, date):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip()
    if not s:
        return ""
    if "T" in s:
        s = s.split("T", 1)[0]
    elif " " in s:
        s = s.split(" ", 1)[0]
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return s


def _format_hora_br(val: Any) -> str:
    if val is None or val == "":
        return ""
    h = str(val).strip()
    if len(h) >= 5 and h[2] == ":":
        return h[:5]
    return h


def _format_segundos_hhmmss(segundos: float) -> str:
    total = max(0, int(segundos))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def relatorio_gestao_sem_conteudo(kpi: GestaoKpiResumo) -> bool:
    """Dia/período sem agendamentos e sem atendimentos com atividade."""
    return kpi.total <= 0


def deve_omitir_relatorio_periodico_vazio(
    kpi: GestaoKpiResumo,
    *,
    tipo_relatorio: TipoRelatorioGestao,
    skip_env: str = "PRODESP_GESTAO_RELATORIO_SKIP_VAZIO",
) -> bool:
    """True quando SKIP_VAZIO está ativo e o período não tem agenda nem atividade."""
    if tipo_relatorio != "periodico":
        return False
    if not _env_bool(skip_env, default=True):
        return False
    return relatorio_gestao_sem_conteudo(kpi)


def deve_omitir_periodico_dia_encerrado(
    rows: list[dict[str, Any]],
    *,
    tipo_relatorio: TipoRelatorioGestao,
    kpi: GestaoKpiResumo | None = None,
) -> bool:
    """True quando o periódico deve ceder ao Report Final (sem atendimento em aberto)."""
    if tipo_relatorio != "periodico":
        return False
    return elegivel_report_final(rows, kpi)


def count_atendimentos_ativos(rows: list[dict[str, Any]]) -> int:
    """Atendimentos do dia ainda em aberto (somente Em Atendimento).

    Concluído Parcial conta como finalizado para Report Final / omitir periódico.
    """
    total = 0
    for row in rows:
        if row_somente_agendado(row):
            continue
        status = (row.get("status_atendimentos") or "").strip()
        if status in STATUS_ATENDIMENTO_ATIVO:
            total += 1
    return total


def elegivel_report_final(
    rows: list[dict[str, Any]],
    kpi: GestaoKpiResumo | None = None,
) -> bool:
    """Report Final quando houve atividade no dia e não resta atendimento em aberto."""
    resumo = kpi or calcular_kpis_gestao(rows)
    if resumo.com_atividade <= 0:
        return False
    return count_atendimentos_ativos(rows) == 0


def calcular_kpis_gestao(rows: list[dict[str, Any]]) -> GestaoKpiResumo:
    """Espelha os KPIs macro do dashboard (updateStats)."""
    resumo = GestaoKpiResumo()
    tempos: list[int] = []

    for row in rows:
        if row_somente_agendado(row):
            resumo.agendados += 1
            continue

        resumo.com_atividade += 1
        status = (row.get("status_atendimentos") or "").strip()
        sub = (row.get("substatus_atendimentos") or "").strip()

        if status == "Em Atendimento":
            resumo.em_atendimento += 1
            if sub == SUBSTATUS_AGUARDANDO_CLIENTE:
                resumo.aguardando_cliente += 1
            elif sub in (SUBSTATUS_AGUARDA_GESTAO, SUBSTATUS_LEGACY_TRIAGEM):
                resumo.aguarda_gestao += 1
            elif is_substatus_aguarda_contratada(sub):
                resumo.aguarda_contratada += 1
            elif sub == SUBSTATUS_AGUARDA_LICENCA:
                resumo.aguarda_licenca += 1
        elif status == "Concluído Parcial":
            resumo.parcial += 1
        elif status == "Concluído" and sub == "Concluído":
            resumo.migrados += 1
        elif status == "Quebra":
            resumo.quebra += 1
        elif status == "Quebra TBRA":
            resumo.quebra_tbra += 1

        seg = row.get("tempo_em_segundos")
        if seg is not None:
            try:
                v = int(seg)
                if v > 0:
                    tempos.append(v)
            except (TypeError, ValueError):
                pass

    resumo.total = resumo.agendados + resumo.com_atividade
    resumo.pct_migrados = calc_pct_migrados_gestao(resumo.migrados, resumo.total)
    if tempos:
        denominador = max(1, resumo.com_atividade)
        resumo.tempo_medio = _format_segundos_hhmmss(sum(tempos) / denominador)
    return resumo


def kpis_por_contratada(rows: list[dict[str, Any]]) -> dict[str, GestaoKpiResumo]:
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grupos[contratada_row_key(row)].append(row)
    return {k: calcular_kpis_gestao(v) for k, v in sorted(grupos.items())}


def _nome_unidade_display(row: Mapping[str, Any]) -> str:
    acr = (row.get("acronimo") or "").strip()
    nome = (row.get("nome") or "").strip()
    if acr:
        return f"{acr} — {nome}" if nome else acr
    return nome


def _ticket_noc_linha(row: Mapping[str, Any]) -> str:
    return str(row.get("ticket_noc") or row.get("ticket_noc_unidades") or "").strip()


def linhas_relatorio_executivo(
    rows: list[dict[str, Any]],
    por_atendimento: dict[int, list],
    por_unidade_sem_att: dict[int, list],
    por_substatus: dict[int, list] | None = None,
    metricas_por_att: dict[int, dict[str, str]] | None = None,
    motivos_por_att: dict[int, str] | None = None,
    *,
    variant: RelatorioVariant = "gestao",
) -> list[dict[str, str]]:
    from prodesp.app import _prodesp_format_row_hora_agendamento, _prodesp_normalizar_hora_agendamento

    metricas_por_att = metricas_por_att or {}
    motivos_por_att = motivos_por_att or {}
    saida: list[dict[str, str]] = []
    for row in rows:
        hora_norm = _prodesp_normalizar_hora_agendamento(row.get("hora_agendamento"))
        fmt_h = {"hora_agendamento": hora_norm}
        _prodesp_format_row_hora_agendamento(fmt_h, "hora_agendamento")
        data_att = row.get("data_atendimentos") or row.get("data_atendimento")
        somente_agenda = row_somente_agendado(row)
        hora_inicio = row.get("horario_inicio") or row.get("horario_inicio_atendimentos")
        hora_fim = row.get("horario_finalizacao") or row.get("horario_finalizacao_atendimentos")
        id_att = row.get("id_atendimento") or row.get("id_atendimentos")
        id_int = int(id_att) if id_att not in (None, "") else None
        metricas = metricas_por_att.get(id_int, {}) if id_int else {}
        linha = {
            "ID VGR": str(row.get("id_vgr") or "").strip(),
            "Data Agendamento": _format_data_br(row.get("data_agendamento")),
            "Hora Agendamento": fmt_h.get("hora_agendamento") or "",
            "Data Atendimento": _format_data_br(data_att) if not somente_agenda else "",
            "Status": (row.get("status_atendimentos") or "Agendado").strip(),
            "Substatus": (row.get("substatus_atendimentos") or "").strip() if not somente_agenda else "",
            "Motivo": motivos_por_att.get(id_int, "") if id_int else "",
            "Contratada": contratada_row_key(row),
            "Início da Atividade": _format_hora_br(hora_inicio) if not somente_agenda else "",
            "Horário Finalização": _format_hora_br(hora_fim) if not somente_agenda else "",
            "Observações": _observacoes_linha(
                row, por_atendimento, por_unidade_sem_att, por_substatus
            ),
            "Nome Unidade": _nome_unidade_display(row),
            "Endereço": (row.get("endereco") or "").strip(),
            "Cidade": (row.get("municipio") or "").strip(),
            "UF": (row.get("estado") or "").strip(),
        }
        if variant == "gestao":
            linha["Tck NOC"] = _ticket_noc_linha(row)
            linha[COL_TEMPO_VITA] = metricas.get(COL_TEMPO_VITA, "00:00:00") if not somente_agenda else ""
            linha[COL_TEMPO_ATENDIMENTO] = metricas.get(
                COL_TEMPO_ATENDIMENTO, "00:00:00"
            ) if not somente_agenda else ""
            for col in colunas_tempo_etapa():
                linha[col] = metricas.get(col, "00:00:00") if not somente_agenda else ""
        saida.append(linha)
    return saida


def _gerar_xlsx_anexo(
    linhas: list[dict[str, str]],
    start_date: str,
    end_date: str,
    *,
    tipo_relatorio: TipoRelatorioGestao = "periodico",
    variant: RelatorioVariant = "gestao",
) -> Optional[dict[str, Any]]:
    if not linhas:
        return None
    try:
        from prodesp.app import _prodesp_aplicar_layout_planilha_relatorio

        cols = colunas_relatorio(variant)
        df = pd.DataFrame(linhas, columns=cols)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Atendimentos", index=False, startrow=1)
            _prodesp_aplicar_layout_planilha_relatorio(
                writer.sheets["Atendimentos"],
                start_date,
                end_date,
            )
        raw = buf.getvalue()
        if start_date == end_date:
            slug = start_date.replace("-", "")
        else:
            slug = f"{start_date.replace('-', '')}_a_{end_date.replace('-', '')}"
        sufixo = "_report_final" if tipo_relatorio == "final" else ""
        prefixo_arq = "relatorio_prodesp_tbra" if variant == "tbra" else "relatorio_prodesp_executivo"
        nome = f"{prefixo_arq}_{slug}{sufixo}.xlsx"
        return {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": nome,
            "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "contentBytes": base64.b64encode(raw).decode("ascii"),
        }
    except Exception as exc:
        logger.warning("prodesp - relatório gestão: falha ao gerar XLSX (%s)", exc)
        return None


_KPI_PER_ROW = 4
_KPI_CARD_HEIGHT = 76
_MSO_VAL = "font-size:24px;font-weight:700;color:#222222;line-height:1.1;mso-line-height-rule:exactly;"
_MSO_LBL = "font-size:12px;color:#444444;text-transform:uppercase;letter-spacing:.3px;line-height:1.2;mso-line-height-rule:exactly;"
_MSO_HINT = (
    "font-size:11px;color:#666666;margin-top:2px;line-height:1.2;"
    "height:16px;mso-line-height-rule:exactly;overflow:hidden;"
)

_MODERN_VAL = "font-size:28px;font-weight:700;color:#222222;line-height:1.1;margin:6px 0 4px 0;"
_MODERN_LBL = "font-size:13px;color:#444444;text-transform:uppercase;letter-spacing:.4px;"
_MODERN_HINT = "font-size:12px;color:#666666;margin-top:4px;"
_MODERN_CARD_WIDTH = "132px"
_MSO_BORDER = "border-top:1px solid #e5e5e5;border-right:1px solid #e5e5e5;border-bottom:1px solid #e5e5e5;"


def _kpi_cards_spec(kpi: GestaoKpiResumo) -> list[tuple[str, str, str, str]]:
    hint_total = f"{kpi.agendados} agendados + {kpi.com_atividade} ativos"
    return [
        ("Total no período", str(kpi.total), hint_total, "#6b2d8a"),
        ("Agendados", str(kpi.agendados), "Sem atividade iniciada", "#6c757d"),
        ("Em atendimento", str(kpi.em_atendimento), "", "#0d6efd"),
        ("Aguarda Gestão", str(kpi.aguarda_gestao), "Substatus", "#6c757d"),
        ("Aguardando cliente", str(kpi.aguardando_cliente), "Substatus", "#fd7e14"),
        ("Aguarda Contratada", str(kpi.aguarda_contratada), "Substatus", "#e67e22"),
        ("Aguarda Licença", str(kpi.aguarda_licenca), "Substatus", "#e67e22"),
        ("Quebra", str(kpi.quebra), "", "#dc3545"),
        ("Quebra TBRA", str(kpi.quebra_tbra), "", "#b02a37"),
        ("Parcial", str(kpi.parcial), "", "#0dcaf0"),
        ("Migrados", str(kpi.migrados), "Status Concluído + substatus Concluído", "#198754"),
        (
            "% migrados",
            f"{kpi.pct_migrados}%",
            (
                f"{kpi.migrados} ÷ {kpi.total} no período"
                if kpi.total > 0
                else "Migrados ÷ total no período"
            ),
            "#198754",
        ),
        ("Tempo médio", kpi.tempo_medio, "Média (todos c/ atividade)", "#6b2d8a"),
    ]


def _kpi_card_cell_html(label: str, valor: str, hint: str, accent: str) -> str:
    hint_text = html.escape(hint) if hint else "&nbsp;"
    h = _KPI_CARD_HEIGHT
    vml_bar = (
        "<v:rect xmlns:v='urn:schemas-microsoft-com:vml' fill='true' stroke='false' "
        f"style='height:{h}px;width:4px;'>"
        f"<v:fill type='solid' color='{accent}' />"
        "</v:rect>"
    )
    return (
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' height='{h}' "
        f"style='border-collapse:collapse;width:100%;height:{h}px;"
        f"mso-table-lspace:0pt;mso-table-rspace:0pt;'>"
        "<tr>"
        f"<td width='4' bgcolor='{accent}' valign='top' height='{h}' "
        f"style='padding:0;background-color:{accent};width:4px;height:{h}px;"
        f"font-size:0;line-height:0;mso-line-height-rule:exactly;mso-padding-alt:0;'>"
        f"{vml_bar}"
        "</td>"
        f"<td valign='top' height='{h}' style='padding:7px 10px 5px 10px;{_MSO_BORDER}"
        f"background:#ffffff;font-family:Calibri,Arial,sans-serif;height:{h}px;"
        f"mso-line-height-rule:exactly;'>"
        f"<div style='{_MSO_LBL}'>{html.escape(label)}</div>"
        f"<div style='{_MSO_VAL}'>{html.escape(str(valor))}</div>"
        f"<div style='{_MSO_HINT}'>{hint_text}</div>"
        "</td></tr></table>"
    )


def _kpi_grid_empty_cell_html() -> str:
    h = _KPI_CARD_HEIGHT
    return (
        f"<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' height='{h}' "
        f"style='border-collapse:collapse;width:100%;height:{h}px;'>"
        f"<tr><td height='{h}' style='height:{h}px;font-size:0;line-height:0;'>&nbsp;</td></tr></table>"
    )


def _kpi_grid_table_html(kpi: GestaoKpiResumo) -> str:
    """Grade de KPIs em tabelas (compatível com Outlook clássico, cards uniformes)."""
    cards = _kpi_cards_spec(kpi)
    h = _KPI_CARD_HEIGHT
    rows_html: list[str] = []
    for i in range(0, len(cards), _KPI_PER_ROW):
        chunk = cards[i : i + _KPI_PER_ROW]
        cells = []
        for label, valor, hint, accent in chunk:
            cells.append(
                f"<td width='25%' valign='top' height='{h}' "
                f"style='padding:0 6px 8px 0;height:{h}px;width:25%;'>"
                f"{_kpi_card_cell_html(label, valor, hint, accent)}"
                "</td>"
            )
        while len(cells) < _KPI_PER_ROW:
            cells.append(
                f"<td width='25%' valign='top' height='{h}' "
                f"style='padding:0 6px 8px 0;height:{h}px;width:25%;'>"
                f"{_kpi_grid_empty_cell_html()}"
                "</td>"
            )
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    return (
        "<table role='presentation' cellpadding='0' cellspacing='0' border='0' width='100%' "
        "style='border-collapse:collapse;table-layout:fixed;width:100%;"
        "mso-table-lspace:0pt;mso-table-rspace:0pt;'>"
        + "".join(rows_html)
        + "</table>"
    )


def _kpi_card_modern_html(label: str, valor: str, hint: str, accent: str) -> str:
    hint_html = (
        f"<div style='{_MODERN_HINT}'>{html.escape(hint)}</div>"
        if hint
        else ""
    )
    style = (
        "display:inline-block;vertical-align:top;"
        f"width:{_MODERN_CARD_WIDTH};margin:0 8px 12px 0;"
        "padding:12px 14px;border-radius:8px;background:#ffffff;"
        "border:1px solid #e5e5e5;"
        f"border-left:4px solid {accent};"
        "box-shadow:0 1px 3px rgba(0,0,0,.06);"
        "font-family:Calibri,Arial,sans-serif;"
    )
    return (
        f"<div style='{style}'>"
        f"<div style='{_MODERN_LBL}'>{html.escape(label)}</div>"
        f"<div style='{_MODERN_VAL}'>{html.escape(str(valor))}</div>"
        f"{hint_html}"
        "</div>"
    )


def _kpi_grid_modern_html(kpi: GestaoKpiResumo) -> str:
    """Cards inline-block com largura uniforme e altura natural (Outlook Web / novo)."""
    cards = _kpi_cards_spec(kpi)
    parts = [
        _kpi_card_modern_html(label, valor, hint, accent)
        for label, valor, hint, accent in cards
    ]
    return (
        "<div style='font-size:0;line-height:0;max-width:980px;'>"
        + "".join(parts)
        + "</div>"
    )


def _kpi_grid_dual_html(kpi: GestaoKpiResumo) -> str:
    """Classic = tabelas (MSO); Web/novo = cards inline-block."""
    classic = _kpi_grid_table_html(kpi)
    modern = _kpi_grid_modern_html(kpi)
    return (
        "<!--[if mso]>"
        f"{classic}"
        "<![endif]-->"
        "<!--[if !mso]><!-->"
        f"{modern}"
        "<!--<![endif]-->"
    )


def _bloco_kpis_html(titulo: str, kpi: GestaoKpiResumo, *, subtitulo: str = "") -> str:
    sub = (
        f"<p style='margin:0 0 10px 0;color:#666666;font-size:12px;"
        f"font-family:Calibri,Arial,sans-serif;'>{html.escape(subtitulo)}</p>"
        if subtitulo
        else ""
    )
    return (
        f"<h3 style='margin:24px 0 8px 0;font-size:15px;color:#6b2d8a;"
        f"font-family:Calibri,Arial,sans-serif;'>{html.escape(titulo)}</h3>"
        f"{sub}"
        f"{_kpi_grid_dual_html(kpi)}"
    )


def build_gestao_email_html(
    *,
    periodo_label: str,
    gerado_em: str,
    kpi_geral: GestaoKpiResumo,
    kpis_contratada: dict[str, GestaoKpiResumo],
    total_registros: int,
    tipo_relatorio: TipoRelatorioGestao = "periodico",
    variant: RelatorioVariant = "gestao",
) -> str:
    painel_label = "Time TBRA" if variant == "tbra" else "painel de gestão"
    if tipo_relatorio == "final":
        intro = (
            "<p style='margin:0 0 12px 0;padding:10px 14px;background:#198754;color:#ffffff;"
            "font-weight:700;border-radius:4px;'>Report Final — encerramento operacional do dia "
            "(nenhum atendimento em aberto).</p>"
            "<p style='margin:0 0 16px 0;'>Segue o <strong>relatório executivo PRODESP (Report Final)</strong> "
            f"do {painel_label} referente ao período "
        )
    else:
        intro = (
            f"<p style='margin:0 0 16px 0;'>Segue o <strong>relatório executivo PRODESP</strong> "
            f"do {painel_label} referente ao período "
        )
    blocos_contr = "".join(
        _bloco_kpis_html(
            contratada,
            kpi,
            subtitulo=f"{kpi.total} no período ({kpi.agendados} agend. + {kpi.com_atividade} ativos)",
        )
        for contratada, kpi in kpis_contratada.items()
    )
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="max-width:980px;border-collapse:collapse;">
  <tr><td style="font-family:Calibri,Arial,sans-serif;font-size:14px;color:#333333;line-height:1.45;">
  <p style="margin:0 0 12px 0;">Olá,</p>
  {intro}<strong>{html.escape(periodo_label)}</strong>, gerado em <strong>{html.escape(gerado_em)}</strong>.</p>
  {_bloco_kpis_html("Resumo geral", kpi_geral, subtitulo="Visão consolidada do período (atendimentos + agendados)")}
  <h2 style="margin:28px 0 10px 0;font-size:16px;color:#444444;border-bottom:2px solid #eeeeee;padding-bottom:6px;">
    Resumo por contratada
  </h2>
  {blocos_contr or "<p style='color:#666666;'>Nenhuma atividade no período.</p>"}
  <p style="margin-top:20px;color:#666666;font-size:12px;">
    O detalhamento completo ({total_registros} registro(s)) está no anexo XLSX, com o mesmo layout do relatório do {html.escape(painel_label)}.
  </p>
  {build_email_assinatura_vita_html()}
  </td></tr>
</table>
""".strip()


def _carregar_rows_relatorio_gestao(
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    from prodesp.app import (
        _prodesp_carregar_dados_dashboard_periodo,
        get_db_connection_long_running,
    )

    conn = get_db_connection_long_running()
    cursor = None
    try:
        rows, _scheduled, cursor, _conn, _own = _prodesp_carregar_dados_dashboard_periodo(
            start_date, end_date, conn=conn
        )
        return rows
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        conn.close()


def executar_report_final(*, variant: RelatorioVariant = "gestao"):
    """Report Final do dia (1×) conforme a config do report.

    Retorna ``ResultadoEnvio``: ``pendente`` enquanto houver atendimento em aberto
    (o agendador tenta de novo no próximo poll).
    """
    from core.reports.report_settings import carregar_config, omitido

    report_id = "TBRA" if variant == "tbra" else "GESTAO"
    cfg = carregar_config(report_id)
    if not cfg.email_ativo or not cfg.final_enabled:
        return omitido("desabilitado")
    hoje = datetime.now(TZ_SP).date().isoformat()
    rows = _carregar_rows_relatorio_gestao(hoje, hoje)
    kpi = calcular_kpis_gestao(rows)
    if cfg.final_so_com_atividade and kpi.com_atividade <= 0:
        return omitido("sem_atividade")
    if kpi.total <= 0:
        return omitido("sem_dados")
    if count_atendimentos_ativos(rows) > 0:
        return omitido("pendente")
    if variant == "tbra":
        from prodesp.prodesp.gestao.tbra_relatorio_email import enviar_relatorio_tbra_periodo

        res = enviar_relatorio_tbra_periodo(start_date=hoje, end_date=hoje, tipo_relatorio="final")
    else:
        res = enviar_relatorio_gestao_periodo(start_date=hoje, end_date=hoje, tipo_relatorio="final")
    return res.como_resultado()


def tentar_enviar_report_final(
    *,
    variant: RelatorioVariant = "gestao",
) -> bool:
    """Envia Report Final do dia quando não restam atendimentos em aberto."""
    from core.reports.report_settings import report_permitido_no_servidor

    if not report_permitido_no_servidor("TBRA" if variant == "tbra" else "GESTAO"):
        return False
    return executar_report_final(variant=variant).enviado


def enviar_relatorio_gestao_periodo(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    *,
    tipo_relatorio: TipoRelatorioGestao = "periodico",
) -> ResultadoEnvioRelatorioGestao:
    """Monta e envia o relatório executivo do dashboard para os destinatários configurados."""
    return _enviar_relatorio_executivo(
        start_date=start_date,
        end_date=end_date,
        tipo_relatorio=tipo_relatorio,
        variant="gestao",
        env_enabled="PRODESP_GESTAO_RELATORIO_EMAIL_ENABLED",
        env_skip_vazio="PRODESP_GESTAO_RELATORIO_SKIP_VAZIO",
        recipients=recipients_gestao_from_env(),
        subject_titulo="Relatório gestão",
        log_label=(
            "relatório gestão Report Final"
            if tipo_relatorio == "final"
            else "relatório gestão automático"
        ),
        report_id="GESTAO",
    )


def _enviar_relatorio_executivo(
    *,
    start_date: Optional[str],
    end_date: Optional[str],
    tipo_relatorio: TipoRelatorioGestao,
    variant: RelatorioVariant,
    env_enabled: str,
    env_skip_vazio: str,
    recipients: list[str],
    subject_titulo: str,
    log_label: str,
    report_id: str | None = None,
) -> ResultadoEnvioRelatorioGestao:
    if not _env_bool(env_enabled, default=False):
        logger.debug("prodesp - %s e-mail desabilitado", log_label)
        return ResultadoEnvioRelatorioGestao.falha()

    cfg = None
    cc_recipients: list[str] = []
    skip_vazio = _env_bool(env_skip_vazio, default=True)
    parar_encerrado = True
    if report_id:
        from core.reports.report_settings import carregar_config

        cfg = carregar_config(report_id)
        if not cfg.email_ativo:
            logger.info("prodesp - %s desabilitado em Personalização dos reports", log_label)
            return ResultadoEnvioRelatorioGestao.falha()
        recipients = cfg.emails_to
        cc_recipients = cfg.emails_cc
        skip_vazio = cfg.skip_sem_dados
        parar_encerrado = cfg.parar_dia_encerrado

    hoje = datetime.now(TZ_SP).date().isoformat()
    start_date = (start_date or hoje)[:10]
    end_date = (end_date or hoje)[:10]

    from prodesp.app import (
        _prodesp_carregar_dados_dashboard_periodo,
        get_db_connection_long_running,
    )

    conn = get_db_connection_long_running()
    cursor = None
    try:
        rows, _scheduled, cursor, _conn, _own = _prodesp_carregar_dados_dashboard_periodo(
            start_date, end_date, conn=conn
        )
        kpi_geral = calcular_kpis_gestao(rows)
        if (
            tipo_relatorio == "periodico"
            and skip_vazio
            and relatorio_gestao_sem_conteudo(kpi_geral)
        ):
            logger.info(
                "prodesp - %s omitido: %s sem agenda nem atividade",
                log_label,
                start_date,
            )
            return ResultadoEnvioRelatorioGestao.omitido()
        if parar_encerrado and deve_omitir_periodico_dia_encerrado(
            rows,
            tipo_relatorio=tipo_relatorio,
            kpi=kpi_geral,
        ):
            logger.info(
                "prodesp - %s omitido: %s dia encerrado (0 em aberto) — usar Report Final",
                log_label,
                start_date,
            )
            return ResultadoEnvioRelatorioGestao.omitido_encerrado()
        fp = ""
        if cfg is not None:
            from core.reports.report_settings import fingerprint, igual_ao_ultimo

            fp = fingerprint(kpi_geral, kpis_por_contratada(rows))
            if (
                tipo_relatorio == "periodico"
                and cfg.skip_igual
                and igual_ao_ultimo(cfg.report_id, hoje, fp)
            ):
                logger.info("prodesp - %s omitido: dados iguais ao último envio", log_label)
                return ResultadoEnvioRelatorioGestao(omitido_igual=True)

        obs_start, obs_end_ex = date_range_exclusive(start_date, end_date)
        por_att, por_u = _carregar_observacoes_map(cursor, obs_start, obs_end_ex)
        ids_att = [
            int(r.get("id_atendimento") or r.get("id_atendimentos"))
            for r in rows
            if r.get("id_atendimento") or r.get("id_atendimentos")
        ]
        por_sub = _carregar_substatus_historico_map(cursor, ids_att)
        motivos_map = carregar_motivos_map(cursor, ids_att)
        metricas_map: dict[int, dict[str, str]] = {}
        if variant == "gestao":
            logs_map = carregar_logs_substatus_map(cursor, ids_att)
            status_map = carregar_logs_status_map(cursor, ids_att)
            metas = {
                int(r.get("id_atendimento") or r.get("id_atendimentos")): r
                for r in rows
                if r.get("id_atendimento") or r.get("id_atendimentos")
            }
            metricas_map = metricas_map_por_atendimento(
                logs_map,
                TZ_SP,
                status_logs_por_att=status_map,
                metas_por_att=metas,
            )
        linhas = linhas_relatorio_executivo(
            rows,
            por_att,
            por_u,
            por_sub,
            metricas_map,
            motivos_map,
            variant=variant,
        )
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        conn.close()

    kpis_contr = kpis_por_contratada(rows)

    if start_date == end_date:
        periodo_label = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    else:
        d0 = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        d1 = datetime.strptime(end_date, "%Y-%m-%d").strftime("%d/%m/%Y")
        periodo_label = f"{d0} a {d1}"

    gerado_em = datetime.now(TZ_SP).strftime("%d/%m/%Y %H:%M")
    if tipo_relatorio == "final":
        prefixo = "[PRODESP] Report Final — "
    else:
        prefixo = "[PRODESP] "
    subject = (
        f"{prefixo}{subject_titulo} — {periodo_label} — "
        f"{kpi_geral.total} reg. | {kpi_geral.migrados} migrados | {kpi_geral.em_atendimento} em atend."
    )
    html_body = build_gestao_email_html(
        periodo_label=periodo_label,
        gerado_em=gerado_em,
        kpi_geral=kpi_geral,
        kpis_contratada=kpis_contr,
        total_registros=len(linhas),
        tipo_relatorio=tipo_relatorio,
        variant=variant,
    )
    anexo = _gerar_xlsx_anexo(
        linhas,
        start_date,
        end_date,
        tipo_relatorio=tipo_relatorio,
        variant=variant,
    )
    extras = [anexo] if anexo else None

    if send_graph_html_email(
        subject=subject,
        html_body=html_body,
        recipients=recipients,
        cc_recipients=cc_recipients or None,
        log_label=log_label,
        extra_attachments=extras,
        include_logo=True,
    ):
        if cfg is not None:
            from core.reports.report_settings import registrar_envio

            registrar_envio(cfg.report_id, hoje, fp)
        return ResultadoEnvioRelatorioGestao.sucesso()
    return ResultadoEnvioRelatorioGestao.falha()

