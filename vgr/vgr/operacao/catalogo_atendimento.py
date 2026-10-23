"""Catálogo status/substatus de atendimento VGR — base PRODESP (P4).

Fonte única de verdade: SUBSTATUS_POR_STATUS.
SUBSTATUS_ATENDIMENTO_OK é DERIVADO dele, para nunca mais divergir do
que o front oferece no select.
"""
from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
STATUS_AGENDADO = "Agendado"
STATUS_OPERACIONAL = "Em Atendimento"

STATUS_FINAIS: frozenset[str] = frozenset(
    {
        "Concluído",
        "Concluído Parcial",
        "Quebra",
    }
)

# Ordem de exibição no select (evita o sorted() alfabético sem sentido de fluxo).
ORDEM_STATUS: tuple[str, ...] = (
    STATUS_AGENDADO,          # NOVO
    STATUS_OPERACIONAL,
    "Concluído Parcial",
    "Concluído",
    "Quebra",
)

STATUS_ATENDIMENTO_OK: frozenset[str] = frozenset(ORDEM_STATUS)

# ---------------------------------------------------------------------------
# Substatus
# ---------------------------------------------------------------------------
# Fluxo principal PRODESP (docs/vgr/08 + prodesp/docs/substatus-e-permissoes.md)
SUBSTATUS_FLUXO: tuple[str, ...] = (
    "Aguarda Cliente",
    "Aguarda Contratada",
    "Aguarda Gestão",
    "Aguardando Config. Remota",
    "Em Configuração Remota",
    "Aguardando Config. MPLS",
    "Em Configuração do MPLS",
    "Aguardando Caderno de Teste",
    "Em Caderno de Teste",
)

# NOVO — fase de preparação/agenda (não inicia atendimento, não trava analista)
SUBSTATUS_AGENDADO: tuple[str, ...] = (
    "Check-list",
    "Aprovado",
    "Recusado",
    "Não Realizado",
)

# NOVO — fechamento
SUBSTATUS_CONCLUIDO: tuple[str, ...] = (
    "Day After",
    "Concluído",
)

SUBSTATUS_QUEBRA: tuple[str, ...] = (
    "Quebra Field",
    "Quebra Cliente",
    "Quebra Hardware",
    "Quebra Link",
    "Quebra Infra",
    "Quebra Vita",
)

SUBSTATUS_CONCLUIDO_PARCIAL: tuple[str, ...] = (
    "Pendente Configuração Remota",
    "Pendente Configuração MPLS",
    "Pendente Link IPD",
    "Pendente Link MPLS",
)

# Legado / valores que podem existir em base antiga e precisam continuar aceitos
# (não são oferecidos no select de novos registros).
SUBSTATUS_EXTRAS: frozenset[str] = frozenset(
    {
        "Com Suporte",
        "Quebra SCI",
        "Quebra Técnica",
        "Quebra Circuito",
        "Quebra Equipamento",
    }
)

# (front popula o select a partir daqui) <<<
SUBSTATUS_POR_STATUS: dict[str, list[str]] = {
    STATUS_AGENDADO: list(SUBSTATUS_AGENDADO),
    STATUS_OPERACIONAL: list(SUBSTATUS_FLUXO),
    "Concluído Parcial": list(SUBSTATUS_CONCLUIDO_PARCIAL),
    "Concluído": list(SUBSTATUS_CONCLUIDO),
    "Quebra": list(SUBSTATUS_QUEBRA),
}

# Derivado do mapa acima — corrige o "Substatus de atendimento inválido."
SUBSTATUS_ATENDIMENTO_OK: frozenset[str] = frozenset(
    {sub for lista in SUBSTATUS_POR_STATUS.values() for sub in lista}
) | SUBSTATUS_EXTRAS

SUBSTATUS_PRE_INICIO: frozenset[str] = frozenset({"Aguarda Gestão"})

# Substatus assumido quando o payload não traz nenhum (POST completo).
SUBSTATUS_PADRAO_POR_STATUS: dict[str, str] = {
    STATUS_AGENDADO: "Check-list",
    STATUS_OPERACIONAL: "Aguarda Gestão",
    "Concluído Parcial": "Pendente Configuração Remota",
    "Concluído": "Concluído",
    "Quebra": "Quebra Field",
}


# ---------------------------------------------------------------------------
# Normalização tolerante (acentos / caixa / espaços) — só para COMPARAR
# ---------------------------------------------------------------------------
def _chave(texto: str | None) -> str:
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.casefold().split())


_INDICE_STATUS: dict[str, str] = {_chave(s): s for s in ORDEM_STATUS}
_INDICE_PAR: dict[tuple[str, str], tuple[str, str]] = {
    (_chave(st), _chave(sb)): (st, sb)
    for st, lista in SUBSTATUS_POR_STATUS.items()
    for sb in lista
}
_INDICE_SUB_GERAL: dict[str, str] = {_chave(s): s for s in SUBSTATUS_ATENDIMENTO_OK}
_INDICE_EXTRAS: dict[str, str] = {_chave(s): s for s in SUBSTATUS_EXTRAS}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def is_status_final(status: str | None) -> bool:
    return (status or "").strip() in STATUS_FINAIS


def is_status_agendado(status: str | None) -> bool:
    """NOVO — True para o status 'Agendado' (fase de preparação)."""
    return (status or "").strip() == STATUS_AGENDADO


def is_substatus_gestao(sub: str | None) -> bool:
    return (sub or "").strip() in SUBSTATUS_PRE_INICIO


def substatus_de_status(status: str | None) -> list[str]:
    """Substatus válidos de um status (usado por front e validator)."""
    return list(SUBSTATUS_POR_STATUS.get((status or "").strip(), []))


def substatus_padrao(status: str | None) -> str | None:
    """Substatus default de um status (usado no create/POST completo)."""
    st = (status or "").strip()
    padrao = SUBSTATUS_PADRAO_POR_STATUS.get(st)
    if padrao:
        return padrao
    lista = substatus_de_status(st)
    return lista[0] if lista else None


def resolver_par_status_substatus(
    status: str | None,
    substatus: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Retorna (status_canon, substatus_canon, mensagem_de_erro|None).

    - Corrige acentuação/caixa ("concluido" -> "Concluído");
    - Valida o PAR status+substatus (era isso que estava errado);
    - Aceita legado em SUBSTATUS_EXTRAS para não travar edição de registros antigos.
    """
    st_raw = (status or "").strip()
    sb_raw = (substatus or "").strip()

    st = _INDICE_STATUS.get(_chave(st_raw)) if st_raw else None
    if st_raw and not st:
        return (st_raw, sb_raw or None, f"Status de atendimento inválido: '{st_raw}'.")

    if not sb_raw:
        return (st, None, None)

    # 1) par exato do catálogo
    par = _INDICE_PAR.get((_chave(st_raw), _chave(sb_raw)))
    if par:
        return (par[0], par[1], None)

    # 2) substatus conhecido, mas sem status informado (PUT parcial)
    if not st:
        canon = _INDICE_SUB_GERAL.get(_chave(sb_raw)) or _INDICE_EXTRAS.get(_chave(sb_raw))
        if canon:
            return (None, canon, None)
        return (None, sb_raw, f"Substatus de atendimento inválido: '{sb_raw}'.")

    # 3) legado: aceita, mas não oferece no select
    canon_extra = _INDICE_EXTRAS.get(_chave(sb_raw))
    if canon_extra:
        return (st, canon_extra, None)

    permitidos = ", ".join(substatus_de_status(st)) or "—"
    return (
        st,
        sb_raw,
        f"Substatus '{sb_raw}' não pertence ao status '{st}'. Opções válidas: {permitidos}.",
    )


def validar_par_status_substatus(status: str | None, substatus: str | None) -> str | None:
    """Apenas a mensagem de erro (None = válido)."""
    _, _, erro = resolver_par_status_substatus(status, substatus)
    return erro


def catalogo_payload() -> dict:
    return {
        "status": list(ORDEM_STATUS),
        "status_finais": sorted(STATUS_FINAIS),
        "status_agendado": STATUS_AGENDADO,
        "substatus_por_status": {k: list(v) for k, v in SUBSTATUS_POR_STATUS.items()},
        "substatus_padrao_por_status": dict(SUBSTATUS_PADRAO_POR_STATUS),
        "substatus_pre_inicio": sorted(SUBSTATUS_PRE_INICIO),
    }