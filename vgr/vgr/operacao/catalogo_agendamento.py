"""Catálogo status de agendamento VGR — legado + Agendado (P4)."""

from __future__ import annotations

STATUS_AGENDADO = "Agendado"
STATUS_IMPRODUTIVA = "Improdutiva"
STATUS_DEFAULT = "Pendente envio a logística"

STATUS_AGENDAMENTO_OK: tuple[str, ...] = (
    "Pendente envio a logística",
    "Aguardando retorno logística",
    "Aguardando retorno fornecedor",
    STATUS_AGENDADO,
    "Técnico em deslocamento",
    "Técnico em atendimento",
    STATUS_IMPRODUTIVA,
    "Agendamento concluído",
    "Finalizado",
)

STATUS_AGENDAMENTO_SET: frozenset[str] = frozenset(STATUS_AGENDAMENTO_OK)

TIPO_AGENDAMENTO_OK: frozenset[str] = frozenset({"Prateleira", "Projeto Especial"})

# Sugestão P11-B: final atendimento → status agenda sugerido
SUGESTAO_POR_STATUS_ATENDIMENTO: dict[str, str] = {
    "Concluído": "Agendamento concluído",
    "Concluído Parcial": "Agendamento concluído",
    "Quebra": STATUS_IMPRODUTIVA,
    "Quebra TBRA": STATUS_IMPRODUTIVA,
}

CHECKLIST_FIELDS: tuple[str, ...] = (
    "q_compra_equip",
    "q_equip_mam",
    "q_email_agendamento",
    "q_lote",
    "q_ticket_aberto",
    "q_confirma_csi_gp",
    "q_tem_problema",
)


def catalogo_payload() -> dict:
    return {
        "status": list(STATUS_AGENDAMENTO_OK),
        "status_agendado": STATUS_AGENDADO,
        "status_improdutiva": STATUS_IMPRODUTIVA,
        "tipos": sorted(TIPO_AGENDAMENTO_OK),
        "checklist": list(CHECKLIST_FIELDS),
        "sugestao_por_status_atendimento": dict(SUGESTAO_POR_STATUS_ATENDIMENTO),
    }
