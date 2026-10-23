"""
Relatório executivo PRODESP — Time TBRA (mesmos KPIs do dashboard, planilha enxuta).
"""
from __future__ import annotations

import os
from typing import Optional

from prodesp.prodesp.gestao.gestao_relatorio_email import (
    ResultadoEnvioRelatorioGestao,
    TipoRelatorioGestao,
    _enviar_relatorio_executivo,
)

DEFAULT_TBRA_RECIPIENTS = [
    "elisangelad.oliveira@telefonica.com",
    "betania.silva@telefonica.com",
    "ana.almeida@telefonica.com",
    "jaqueline.lemes@telefonica.com",
    "douglas.francisco@telefonica.com",
    "carlos.felix@telefonica.com",
    "rubia.ongaratto@telefonica.com",
    "fabiob.silva@telefonica.com",
    "aline.zsilva@telefonica.com",
    "rogerio.toledo@telefonica.com",
    "pedro.hmartins@telefonica.com",
]


def recipients_tbra_from_env() -> list[str]:
    raw = (os.getenv("PRODESP_TIME_TBRA_RELATORIO_EMAIL_TO") or "").strip()
    if raw:
        return [e.strip() for e in raw.replace(",", ";").split(";") if e.strip()]
    return list(DEFAULT_TBRA_RECIPIENTS)


def enviar_relatorio_tbra_periodo(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    *,
    tipo_relatorio: TipoRelatorioGestao = "periodico",
) -> ResultadoEnvioRelatorioGestao:
    """Envia relatório TBRA (KPIs iguais ao gestão; XLSX sem Tck NOC, horários e colunas de tempo/etapa)."""
    return _enviar_relatorio_executivo(
        start_date=start_date,
        end_date=end_date,
        tipo_relatorio=tipo_relatorio,
        variant="tbra",
        env_enabled="PRODESP_TIME_TBRA_RELATORIO_EMAIL_ENABLED",
        env_skip_vazio="PRODESP_TIME_TBRA_RELATORIO_SKIP_VAZIO",
        recipients=recipients_tbra_from_env(),
        subject_titulo="Relatório TBRA",
        log_label=(
            "relatório TBRA Report Final"
            if tipo_relatorio == "final"
            else "relatório TBRA automático"
        ),
        report_id="TBRA",
    )


def tentar_enviar_report_final_tbra() -> bool:
    """Atalho: Report Final TBRA do dia (mesmo corpo/anexo da variante tbra)."""
    from prodesp.prodesp.gestao.gestao_relatorio_email import tentar_enviar_report_final

    return tentar_enviar_report_final(variant="tbra")
