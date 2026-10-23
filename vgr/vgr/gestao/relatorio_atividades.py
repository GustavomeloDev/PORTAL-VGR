"""Relatório de Atividades VGR (download manual da Gestão de Atendimentos).

- XLSX: abas «Resumo», «Atividades» e «Transições» (layout no padrão do
  relatório PRODESP: título, cabeçalho destacado, zebra, filtro e painel fixo).
- CSV: somente «Atividades», ``;`` + BOM UTF-8 (Excel PT-BR), igual PRODESP.

Segurança: valores iniciados por = + - @ (e TAB/CR) recebem apóstrofo
para não virarem fórmula no Excel (CSV/Formula injection).
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from typing import Any, Iterable

from vgr.vgr.gestao.gestao_kpis import (
    escopo_linha,
    fmt_hhmmss,
    status_exibicao,
    tempo_atendimento_segundos,
    to_date,
    to_datetime,
)

COLUNAS_ATIVIDADES: list[str] = [
    "Escopo",
    "ID Atendimento",
    "Cliente",
    "Unidade",
    "Cidade",
    "UF",
    "ID VGR SDWAN",
    "ID VGR SDWIFI",
    "ID VGR SDLAN",
    "Data Agend.",
    "Hora Agend.",
    "Status Agend.",
    "Contratada",
    "Field",
    "Data Atividade",
    "Fechamento",
    "Status",
    "Substatus",
    "Analista",
    "Tempo Atendimento",
]

COLUNAS_TRANSICOES: list[str] = [
    "Data/Hora",
    "ID Atendimento",
    "Cliente",
    "Unidade",
    "Status anterior",
    "Substatus anterior",
    "Status novo",
    "Substatus novo",
    "Usuário",
    "Observação",
]

_LARGURAS = {
    "Escopo": 20,
    "ID Atendimento": 13,
    "Cliente": 30,
    "Unidade": 30,
    "Cidade": 18,
    "UF": 6,
    "ID VGR SDWAN": 15,
    "ID VGR SDWIFI": 15,
    "ID VGR SDLAN": 15,
    "Data Agend.": 12,
    "Hora Agend.": 10,
    "Status Agend.": 22,
    "Contratada": 22,
    "Field": 22,
    "Data Atividade": 17,
    "Fechamento": 17,
    "Status": 18,
    "Substatus": 26,
    "Analista": 24,
    "Tempo Atendimento": 14,
    "Data/Hora": 17,
    "Status anterior": 18,
    "Substatus anterior": 26,
    "Status novo": 18,
    "Substatus novo": 26,
    "Usuário": 26,
    "Observação": 48,
    "Indicador": 34,
    "Valor": 14,
}

_CENTRO = {
    "ID Atendimento",
    "UF",
    "Data Agend.",
    "Hora Agend.",
    "Data Atividade",
    "Fechamento",
    "Tempo Atendimento",
    "Data/Hora",
    "Valor",
}

_WRAP = {"Observação"}

_PREFIXOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------
def _txt(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    # «-» isolado é placeholder comum (Field/contato ausente) — não é fórmula.
    if len(s) > 1 and s.startswith(_PREFIXOS_FORMULA):
        return "'" + s
    return s


def _br_date(value: Any) -> str:
    d = to_date(value)
    return d.strftime("%d/%m/%Y") if d else ""


def _br_datetime(value: Any) -> str:
    dt = to_datetime(value)
    return dt.strftime("%d/%m/%Y %H:%M") if dt else ""


def _br_time(value: Any) -> str:
    """TIME do MySQL chega como timedelta; strings HH:MM[:SS] também aceitas."""
    if value is None or value == "":
        return ""
    if isinstance(value, timedelta):
        total = max(int(value.total_seconds()), 0)
        hh, rem = divmod(total, 3600)
        return f"{hh:02d}:{rem // 60:02d}"
    s = str(value).strip()
    return s[:5] if len(s) >= 5 else s


def linha_atividade(row: dict[str, Any], start: date, end: date) -> list[str]:
    seg = tempo_atendimento_segundos(row)
    id_at = row.get("id_atendimento")
    status, substatus = status_exibicao(row)
    return [
        _txt(escopo_linha(row, start, end)),
        _txt(id_at),
        _txt(row.get("razao_social")),
        _txt(row.get("nome_unidade")),
        _txt(row.get("cidade")),
        _txt(row.get("uf")),
        _txt(row.get("id_vgr_sdwan")),
        _txt(row.get("id_vgr_sdwifi")),
        _txt(row.get("id_vgr_sdlan")),
        _br_date(row.get("data_agendamento")),
        _br_time(row.get("hora_agendamento")),
        _txt(row.get("status_agendamento")),
        _txt(row.get("contratada_atendimento") or row.get("contratada_planejada")),
        _txt(row.get("field_atendimento") or row.get("field_agendamento")),
        _br_datetime(row.get("data_atividade")) if id_at else "",
        _br_datetime(row.get("fechamento")),
        _txt(status),
        _txt(substatus),
        _txt(row.get("analista_atuante")),
        fmt_hhmmss(seg) if seg is not None else "",
    ]


def linha_transicao(row: dict[str, Any]) -> list[str]:
    quem = " – ".join(
        p for p in (_txt(row.get("usuario_re")), _txt(row.get("usuario_nome"))) if p
    )
    return [
        _br_datetime(row.get("criado_em")),
        _txt(row.get("id_atendimento")),
        _txt(row.get("razao_social")),
        _txt(row.get("nome_unidade")),
        _txt(row.get("status_anterior")),
        _txt(row.get("substatus_anterior")),
        _txt(row.get("status_novo")),
        _txt(row.get("substatus_novo")),
        _txt(quem),
        _txt(row.get("observacao")),
    ]


def linhas_resumo(payload: dict[str, Any]) -> list[list[Any]]:
    k = payload.get("kpis") or {}
    det = payload.get("detalhe_total") or {}
    return [
        ["Total no período", k.get("total", 0)],
        ["Agendados (sem atividade iniciada)", k.get("agendados", 0)],
        ["Com atividade", k.get("com_atividade", 0)],
        ["Em Atendimento", k.get("em_atendimento", 0)],
        ["Aguarda Cliente", k.get("aguarda_cliente", 0)],
        ["Aguarda Contratada", k.get("aguarda_contratada", 0)],
        ["Aguarda Gestão", k.get("aguarda_gestao", 0)],
        ["Fluxo técnico (Config./MPLS/Caderno)", k.get("fluxo_tecnico", 0)],
        ["Quebra", k.get("quebra", 0)],
        ["Concluído Parcial", k.get("concluido_parcial", 0)],
        ["Concluídos", k.get("concluidos", 0)],
        ["Day After", k.get("day_after", 0)],
        ["% Concluídos", f"{k.get('pct_concluidos', 0)}%"],
        ["Tempo médio (finalizados)", k.get("tempo_medio", "00:00:00")],
        ["Agendas improdutivas (fora do total)", k.get("improdutivas", 0)],
        ["— Agendados pendentes", det.get("agendados_pend", 0)],
        ["— Agendados finalizados", det.get("agendados_finalizados", 0)],
        ["— Agendados ativos", det.get("agendados_ativos", 0)],
        ["— Fora de escopo finalizados", det.get("fora_escopo_finalizados", 0)],
        ["— Fora de escopo ativos", det.get("fora_escopo_ativos", 0)],
    ]


def nome_arquivo(start: date, end: date, fmt: str) -> str:
    return f"relatorio_vgr_atividades_{start.isoformat()}_a_{end.isoformat()}.{fmt}"


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def gerar_csv(rows: Iterable[dict[str, Any]], start: date, end: date) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(COLUNAS_ATIVIDADES)
    for row in rows or []:
        writer.writerow(linha_atividade(row, start, end))
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------
def _aplicar_layout(ws, headers: list[str], titulo: str, n_linhas: int) -> None:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    ultima_col = get_column_letter(len(headers))
    header_row = 2
    data_start = 3
    max_row = max(header_row + n_linhas, header_row)

    ws.merge_cells(f"A1:{ultima_col}1")
    ws["A1"] = titulo
    ws["A1"].font = Font(bold=True, size=13, color="3C0062")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24

    fill_header = PatternFill("solid", fgColor="3C0062")
    fill_zebra = PatternFill("solid", fgColor="F3EEF7")
    lado = Side(style="thin", color="D9D2E0")
    borda = Border(left=lado, right=lado, top=lado, bottom=lado)
    font_header = Font(bold=True, color="FFFFFF", size=10)
    font_body = Font(size=10)

    for col_idx, nome in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=nome)
        cell.fill = fill_header
        cell.font = font_header
        cell.border = borda
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = _LARGURAS.get(nome, 16)
    ws.row_dimensions[header_row].height = 30

    for r in range(data_start, max_row + 1):
        zebra = (r - data_start) % 2 == 1
        for col_idx, nome in enumerate(headers, start=1):
            cell = ws.cell(row=r, column=col_idx)
            cell.font = font_body
            cell.border = borda
            if zebra:
                cell.fill = fill_zebra
            if nome in _WRAP:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            elif nome in _CENTRO:
                cell.alignment = Alignment(horizontal="center", vertical="top")
            else:
                cell.alignment = Alignment(vertical="top")

    ws.freeze_panes = f"A{data_start}"
    if n_linhas:
        ws.auto_filter.ref = f"A{header_row}:{ultima_col}{max_row}"
    ws.sheet_view.showGridLines = False
    ws.print_title_rows = f"1:{header_row}"


def _preencher(ws, linhas: list[list[Any]]) -> None:
    for i, valores in enumerate(linhas, start=3):
        for j, v in enumerate(valores, start=1):
            ws.cell(row=i, column=j, value=v)


def gerar_xlsx(
    rows: list[dict[str, Any]],
    transicoes: list[dict[str, Any]],
    resumo: dict[str, Any],
    start: date,
    end: date,
) -> bytes:
    from openpyxl import Workbook

    periodo_txt = f"{start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}"
    wb = Workbook()

    ws_res = wb.active
    ws_res.title = "Resumo"
    res_linhas = linhas_resumo(resumo)
    _preencher(ws_res, res_linhas)
    _aplicar_layout(
        ws_res,
        ["Indicador", "Valor"],
        f"VGR — Gestão de Atendimentos — {periodo_txt}",
        len(res_linhas),
    )

    ws_at = wb.create_sheet("Atividades")
    at_linhas = [linha_atividade(r, start, end) for r in rows or []]
    _preencher(ws_at, at_linhas)
    _aplicar_layout(
        ws_at,
        COLUNAS_ATIVIDADES,
        f"VGR — Relatório de Atividades — {periodo_txt}",
        len(at_linhas),
    )

    ws_tr = wb.create_sheet("Transições")
    tr_linhas = [linha_transicao(r) for r in transicoes or []]
    _preencher(ws_tr, tr_linhas)
    _aplicar_layout(
        ws_tr,
        COLUNAS_TRANSICOES,
        f"VGR — Transições de status — {periodo_txt}",
        len(tr_linhas),
    )

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
