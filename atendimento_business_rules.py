"""
Regras de negócio PRODESP (atendimentos) — funções puras, testáveis sem Flask/MySQL.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Optional

# Substatus iniciais / legado / paralelos ao fluxo
SUBSTATUS_LEGACY_TRIAGEM = "Triagem"
SUBSTATUS_AGUARDA_GESTAO = "Aguarda Gestão"
SUBSTATUS_COM_SUPORTE = "Com Suporte"
SUBSTATUS_AGUARDANDO_CLIENTE = "Aguardando Cliente"
SUBSTATUS_AGUARDA_CONTRATADA = "Aguarda Contratada"
SUBSTATUS_AGUARDA_LICENCA = "Aguarda Licença"
SUBSTATUS_AGUARDA_CONTRATADA_VALUES = frozenset({SUBSTATUS_AGUARDA_CONTRATADA})
STATUS_QUEBRA_TBRA = "Quebra TBRA"
SUBSTATUS_QUEBRA_TBRA_SCI = "Quebra SCI"
SUBSTATUS_QUEBRA_TBRA_TECNICA = "Quebra Técnica"
SUBSTATUS_INICIAL_FILA = "Aguardando Config. Remota"

SUBSTATUS_AGUARDA_EXTERNO = frozenset({
    SUBSTATUS_AGUARDANDO_CLIENTE,
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_LICENCA,
})

SUBSTATUS_AG_GP_PARALELOS = frozenset({
    SUBSTATUS_AGUARDANDO_CLIENTE,
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_LICENCA,
})

SUBSTATUS_QUEBRA_TBRA_VALUES = frozenset({
    SUBSTATUS_QUEBRA_TBRA_SCI,
    SUBSTATUS_QUEBRA_TBRA_TECNICA,
})


def is_substatus_quebra_normal(substatus: str) -> bool:
    """Substatus válido para status «Quebra» (exclui Quebra SCI/Técnica do TBRA)."""
    s = (substatus or "").strip()
    if not s.startswith("Quebra"):
        return False
    return s not in SUBSTATUS_QUEBRA_TBRA_VALUES


def mensagem_substatus_obrigatorio_quebra() -> str:
    return (
        "Para status «Quebra», selecione um substatus de Quebra válido "
        "(ex.: Quebra Hardware, Quebra Link)."
    )

FINAL_STATUSES_ATENDIMENTO = frozenset({
    "Concluído",
    "Concluído Parcial",
    "Quebra",
    STATUS_QUEBRA_TBRA,
})

SUBSTATUS_GESTAO_VALUES = frozenset({SUBSTATUS_LEGACY_TRIAGEM, SUBSTATUS_AGUARDA_GESTAO})

RETORNO_SUBSTATUS_MIN_CHARS = 10
AGUARDA_GESTAO_MIN_CHARS = 30
COM_SUPORTE_MIN_CHARS = 10
AGUARDA_EXTERNO_MIN_CHARS = 10
QUEBRA_ENCERRAMENTO_MIN_CHARS = 10

# «Em Configuração do MPLS» não entra aqui: analista_mpls é terceiro (lista/outros), sem dono/bloqueio IMPLANTAÇÃO.
SUBSTATUS_TO_ANALYST_COL: dict[str, str] = {
    SUBSTATUS_LEGACY_TRIAGEM: "analista_atuante_atendimentos",
    SUBSTATUS_AGUARDA_GESTAO: "analista_atuante_atendimentos",
    "Em Configuração Remota": "analista_configuracao_atendimentos",
    "Em Caderno de Teste": "analista_caderno_teste_atendimentos",
}

ANALISTAS_MPLS_TERCEIRO_OPCOES: tuple[str, ...] = (
    "Cassio Jose Valeriano De Alcantara",
    "Diego Roberto Rosa Moreira Lima",
    "Edson Francisco Da Silva",
    "Jose Luciano Ferreira De Melo",
    "Persio De Oliveira Bomfim",
    "Rafael Rangel Tofolo",
    "Tiago Vinicius Costa De Souza",
    "Wagner Rodrigues Da Silva",
)

FLUXO_SUBSTATUS_ORDEM: list[str] = [
    SUBSTATUS_AGUARDA_GESTAO,
    "Aguardando Config. Remota",
    "Em Configuração Remota",
    "Aguardando Config. MPLS",
    "Em Configuração do MPLS",
    "Aguardando Caderno de Teste",
    "Em Caderno de Teste",
]

# Filas operacionais após Aguarda Gestão (fluxo Implantação — triagem → fila)
FILAS_AGUARDANDO_APOS_TRIAGEM = frozenset({
    "Aguardando Config. Remota",
    "Aguardando Config. MPLS",
    "Aguardando Caderno de Teste",
})

# Única fila «Aguardando …» operacional para AG/GP (sem MPLS/Caderno)
FILA_AGUARDANDO_GESTAO = frozenset({SUBSTATUS_INICIAL_FILA})

SUBSTATUS_EDICAO_COMPARTILHADA_GESTAO_IMPLANTACAO = frozenset({
    SUBSTATUS_AGUARDANDO_CLIENTE,
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_LICENCA,
})

SUBSTATUS_EDICAO_SOMENTE_GESTAO = frozenset({
    SUBSTATUS_LEGACY_TRIAGEM,
    SUBSTATUS_AGUARDA_GESTAO,
})

SUBSTATUS_EDICAO_AGENDAMENTO_GP = frozenset({
    *SUBSTATUS_EDICAO_SOMENTE_GESTAO,
    *SUBSTATUS_EDICAO_COMPARTILHADA_GESTAO_IMPLANTACAO,
    *FILA_AGUARDANDO_GESTAO,
})

# Espelha login.portal_access_config (NOC = IMPLANTAÇÃO; TBRA = GP) até restrições futuras.
_PERFIS_VISUAL_IMPLANTACAO = frozenset({"IMPLANTAÇÃO", "NOC"})
_PERFIS_EDICAO_RESTRITA = frozenset(
    {
        "AGENDAMENTO",
        "SUPERVISORES",
        "GP",
        "TBRA",
    }
)


def departamentos_do_user_dict(user: Mapping[str, Any]) -> frozenset[str]:
    """União de perfis a partir do dict passado por `_prodesp_user_edicao_map` (ou legado)."""
    raw = user.get("departamentos")
    if raw is not None:
        return frozenset(str(x).strip() for x in raw if x and str(x).strip())
    depts: set[str] = set()
    principal = (user.get("departamento_user") or "").strip()
    if principal:
        depts.add(principal)
    for extra in user.get("departamentos_extras") or []:
        e = (extra or "").strip() if isinstance(extra, str) else str(extra or "").strip()
        if e:
            depts.add(e)
    return frozenset(depts)


def usuario_tem_implantacao_dict(user: Mapping[str, Any]) -> bool:
    return bool(departamentos_do_user_dict(user) & _PERFIS_VISUAL_IMPLANTACAO)


def usuario_usa_regras_edicao_gp_agendamento_restritas_dict(user: Mapping[str, Any]) -> bool:
    """AG/GP/SUPERVISORES com fila restrita; não aplica se também for IMPLANTAÇÃO."""
    if usuario_tem_implantacao_dict(user):
        return False
    return bool(departamentos_do_user_dict(user) & _PERFIS_EDICAO_RESTRITA)

DADOS_FIELD_JS_TO_DB: tuple[tuple[str, str, str], ...] = (
    ("contratada", "contratada_atendimentos", "Contratada"),
    ("field", "field_atendimentos", "Field"),
    ("contato_field", "contato_field_atendimentos", "Contato Field"),
)

# JSON keys do create → mesmas chaves do update
CREATE_UNIT_JSON_KEYS = (
    "nome",
    "endereco",
    "numero",
    "bairro",
    "municipio",
    "estado",
    "complemento",
    "cep",
    "latitude",
    "longitude",
    "telefone_contato",
    "hostname",
    "acronimo",
    "data_agendamento",
    "hora_agendamento",
    "ip_lan_01",
    "ip_lan_transito",
    "id_intragov",
    "loopback_vivo",
    "loopback_cliente",
    "loopback_on_bgp",
    "ticket_noc",
    "mv_ip_transito",
    "mv_mask_transito",
    "mv_ip_swt",
    "mv_rede_voz",
    "mv_mask_voz",
    "mv_rede_lan_assoc",
    "mv_mask_lan_assoc",
    "mv_rede_totem",
    "mv_mask_totem",
    "mv_ip_lan_sec",
    "mv_rede_lan_sec",
    "mv_ip_lan_ter",
    "mv_rede_lan_ter",
    "mv_ip_lan_qua",
    "mv_rede_lan_qua",
    "mv_rede_wifi_guest",
    "mv_ip_wifi_guest",
    "mv_dhcp_start_wifi_guest",
    "mv_dhcp_end_wifi_guest",
    "mv_reserva_start_wifi_guest",
    "mv_reserva_end_wifi_guest",
)

CREATE_ATENDIMENTO_JSON_KEYS = (
    "status",
    "substatus",
    "analista_atuante",
    "analista_configuracao",
    "analista_mpls_atendimentos",
    "analista_caderno_teste",
    "contratada",
    "field",
    "contato_field",
    "logs",
)

# coluna JS de analista → substatus ativo correspondente
JS_ANALYST_FIELD_TO_ACTIVE_SUBSTATUS: dict[str, str] = {
    "analista_atuante": SUBSTATUS_AGUARDA_GESTAO,
    "analista_configuracao": "Em Configuração Remota",
    "analista_caderno_teste": "Em Caderno de Teste",
}


def is_substatus_gestao(substatus: str) -> bool:
    return (substatus or "").strip() in SUBSTATUS_GESTAO_VALUES


def normalizar_substatus_fluxo(substatus: str) -> str:
    """UI usa Aguarda Gestão / Aguarda Contratada; legado no banco pode variar."""
    sub = (substatus or "").strip()
    if sub == SUBSTATUS_LEGACY_TRIAGEM:
        return SUBSTATUS_AGUARDA_GESTAO
    if sub == "Aguarda Fornecedor":
        return SUBSTATUS_AGUARDA_CONTRATADA
    return sub


def is_substatus_aguarda_contratada(substatus: str) -> bool:
    return (substatus or "").strip() in SUBSTATUS_AGUARDA_CONTRATADA_VALUES


def destinos_substatus_permitidos_ag_gp(old_substatus: str) -> frozenset[str]:
    """Substatus que AG/GP/SUPERVISORES pode selecionar a partir do substatus atual."""
    old = (old_substatus or "").strip()
    gestao_vals = frozenset({SUBSTATUS_AGUARDA_GESTAO, SUBSTATUS_LEGACY_TRIAGEM})
    if is_substatus_gestao(old):
        return gestao_vals | SUBSTATUS_AG_GP_PARALELOS | FILA_AGUARDANDO_GESTAO
    if old == SUBSTATUS_INICIAL_FILA:
        return gestao_vals | FILA_AGUARDANDO_GESTAO | SUBSTATUS_AG_GP_PARALELOS
    if old in SUBSTATUS_AG_GP_PARALELOS:
        return gestao_vals | SUBSTATUS_AG_GP_PARALELOS | FILA_AGUARDANDO_GESTAO
    return frozenset()


def mensagem_transicao_substatus_ag_gp_negada(old_substatus: str, new_substatus: str) -> str:
    return (
        f"Seu perfil (Agendamento, GP ou SUPERVISORES) não pode mover o substatus "
        f"de «{normalizar_substatus_fluxo(old_substatus)}» para «{new_substatus}». "
        "Envie apenas para filas «Aguardando …» ou pendências paralelas; "
        "etapas «Em …» são assumidas pelo time de Implantação."
    )


def validar_substatus_create_ag_gp(substatus: str) -> Optional[str]:
    """Create: nasce em Aguardando Config. Remota; AG/GP não pode «Em …» nem destino inválido."""
    sub = normalizar_substatus_fluxo((substatus or "").strip()) or SUBSTATUS_INICIAL_FILA
    if sub == SUBSTATUS_INICIAL_FILA:
        return None
    allowed = destinos_substatus_permitidos_ag_gp(SUBSTATUS_INICIAL_FILA) | frozenset(
        {SUBSTATUS_INICIAL_FILA}
    )
    if sub in allowed:
        return None
    return mensagem_transicao_substatus_ag_gp_negada(SUBSTATUS_INICIAL_FILA, sub)


def validar_transicao_substatus_ag_gp(old_substatus: str, new_substatus: str) -> Optional[str]:
    """Bloqueia AG/GP de avançar para etapas «Em …» (ex.: Em Configuração Remota)."""
    old = (old_substatus or "").strip()
    new = (new_substatus or "").strip()
    if not new or new == old:
        return None
    if new in SUBSTATUS_QUEBRA_TBRA_VALUES or is_substatus_quebra_normal(new):
        if old in SUBSTATUS_EDICAO_AGENDAMENTO_GP:
            return None
    allowed = destinos_substatus_permitidos_ag_gp(old)
    if new in allowed:
        return None
    if is_substatus_gestao(new) and SUBSTATUS_AGUARDA_GESTAO in allowed:
        return None
    return mensagem_transicao_substatus_ag_gp_negada(old, new)


def mensagem_edicao_restrita_ag_gp() -> str:
    return (
        f"Seu perfil (Agendamento, GP ou SUPERVISORES) só pode editar em «{SUBSTATUS_AGUARDA_GESTAO}», "
        f"«{SUBSTATUS_INICIAL_FILA}», ou pendências paralelas "
        f"(«{SUBSTATUS_AGUARDA_LICENCA}», «{SUBSTATUS_AGUARDA_CONTRATADA}», "
        f"«{SUBSTATUS_AGUARDANDO_CLIENTE}»)."
    )


def mensagem_edicao_apenas_gestao() -> str:
    return (
        "Este substatus é exclusivo do time de Agendamento/Gestão. "
        "Somente perfis de Agendamento, GP ou SUPERVISORES podem editar ou movimentar."
    )


def substatus_conta_como_gestao_kpi(substatus: str) -> bool:
    return is_substatus_gestao(substatus)


def _texto_observacoes_novas(observacoes: list | None) -> list[str]:
    textos: list[str] = []
    for obs in observacoes or []:
        if not isinstance(obs, dict):
            continue
        t = (obs.get("observacao_prodesp") or obs.get("observacao") or "").strip()
        if t:
            textos.append(t)
    return textos


def _observacao_atende_minimo(textos: list[str], prefixo: str, min_chars: int) -> bool:
    for t in textos:
        if not t.startswith(prefixo):
            continue
        corpo = t[len(prefixo) :].strip()
        if len(corpo) >= min_chars:
            return True
    return False

UPDATE_SUBSTATUS_ANALYST_JS_FIELDS = frozenset(
    {"substatus"} | set(JS_ANALYST_FIELD_TO_ACTIVE_SUBSTATUS.keys())
)


def _data_atendimento_registro(atendimento_row: Mapping[str, Any]) -> Optional[date]:
    dt_a = atendimento_row.get("data_atendimentos")
    if isinstance(dt_a, datetime):
        return dt_a.date()
    if isinstance(dt_a, date):
        return dt_a
    if dt_a:
        try:
            return datetime.strptime(str(dt_a)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def row_api_para_validacao_edicao(row_api: Mapping[str, Any]) -> dict[str, Any]:
    """
    Mapeia payload da listagem/detalhe PRODESP (chaves curtas do JSON) para
    validar_edicao_atendimento / validar_dono_edicao_atendimento (sufixo _atendimentos).
    """
    return {
        "status_atendimentos": row_api.get("status_atendimento") or "",
        "substatus_atendimentos": row_api.get("substatus_atendimento") or "",
        "data_atendimentos": row_api.get("data_atendimento_raw")
        or row_api.get("data_atendimento"),
        "analista_atuante_atendimentos": row_api.get("analista_atuante") or "",
        "analista_configuracao_atendimentos": row_api.get("analista_configuracao") or "",
        "analista_mpls_atendimentos": row_api.get("analista_mpls_atendimentos") or "",
        "analista_caderno_teste_atendimentos": row_api.get("analista_caderno_teste") or "",
    }


def _normalizar_nome_comparacao(nome: str) -> str:
    return " ".join((nome or "").strip().split()).casefold()


def _substatus_eh_fila_aguardando(substatus: str) -> bool:
    """Filas «Aguardando …» operacionais (sem dono até assumir «Em …»)."""
    substatus = (substatus or "").strip()
    return substatus.startswith("Aguardando") and substatus not in SUBSTATUS_AGUARDA_EXTERNO


def is_transicao_triagem_para_fila_aguardando(old_substatus: str, new_substatus: str) -> bool:
    """Aguarda Gestão (ou Triagem legado) → fila Aguardando Config / MPLS / Caderno."""
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    return is_substatus_gestao(old_substatus) and new_substatus in FILAS_AGUARDANDO_APOS_TRIAGEM


def _valor_js_em_updates(updates: list | None, js_field: str) -> Optional[str]:
    for item in updates or []:
        if (item.get("coluna") or "").strip() == js_field:
            val = item.get("valor")
            return "" if val is None else str(val).strip()
    return None


def dados_field_campos_vazios(
    atendimento_row: Mapping[str, Any],
    updates: list | None = None,
) -> list[str]:
    """Retorna rótulos dos campos Dados Field ainda vazios (considera payload + banco)."""
    vazios: list[str] = []
    for js_key, db_col, label in DADOS_FIELD_JS_TO_DB:
        upd = _valor_js_em_updates(updates, js_key)
        val = upd if upd is not None else (str(atendimento_row.get(db_col) or "")).strip()
        if js_key == "contato_field":
            val = "".join(c for c in val if c.isdigit())
        if not val:
            vazios.append(label)
    return vazios


def mensagem_dados_field_obrigatorios_triagem_fila(campos_vazios: list[str]) -> str:
    lista = ", ".join(campos_vazios) if campos_vazios else "Contratada, Field, Contato Field"
    return (
        f"Para enviar o atendimento de «{SUBSTATUS_AGUARDA_GESTAO}» para a fila Aguardando, "
        f"preencha os Dados Field: {lista}."
    )


def mensagem_dados_field_obrigatorios_create_em_atendimento(campos_vazios: list[str]) -> str:
    lista = ", ".join(campos_vazios) if campos_vazios else "Contratada, Field, Contato Field"
    return (
        "Para iniciar o atendimento com status «Em Atendimento», "
        f"preencha os Dados Field: {lista}."
    )


def dados_field_vazios_do_payload_create(data: Mapping[str, Any] | None) -> list[str]:
    """Campos Dados Field vazios no JSON de /atendimentos/create (chaves JS)."""
    payload = data or {}
    vazios: list[str] = []
    for js_key, _db_col, label in DADOS_FIELD_JS_TO_DB:
        val = str(payload.get(js_key) or "").strip()
        if js_key == "contato_field":
            val = "".join(c for c in val if c.isdigit())
        if not val:
            vazios.append(label)
    return vazios


def check_dados_field_create_em_atendimento(data: Mapping[str, Any] | None) -> Optional[str]:
    """Obriga Dados Field ao criar atendimento já em «Em Atendimento»."""
    status = str((data or {}).get("status") or "").strip()
    if status != "Em Atendimento":
        return None
    vazios = dados_field_vazios_do_payload_create(data)
    if vazios:
        return mensagem_dados_field_obrigatorios_create_em_atendimento(vazios)
    return None


def normalizar_nome_analista_mpls(nome: str) -> str:
    return " ".join((nome or "").split())


def analista_mpls_terceiro_valido(valor: str) -> bool:
    """Nome do analista MPLS (lista fixa ou «Outros» com texto livre)."""
    return len(normalizar_nome_analista_mpls(valor)) >= 3


def is_transicao_para_em_config_mpls(old_substatus: str, new_substatus: str) -> bool:
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    return new_substatus == "Em Configuração do MPLS" and new_substatus != old_substatus


def _analista_mpls_efetivo(
    atendimento_row: Mapping[str, Any],
    updates: list | None = None,
) -> str:
    upd = _valor_js_em_updates(updates, "analista_mpls_atendimentos")
    if upd is not None:
        return upd
    return (str(atendimento_row.get("analista_mpls_atendimentos") or "")).strip()


def _mensagem_analista_mpls_obrigatorio(momento: str) -> str:
    lista = ", ".join(ANALISTAS_MPLS_TERCEIRO_OPCOES)
    return (
        f"{momento} selecione o analista MPLS (time terceiro) ou informe em «Outros». "
        f"Opções: {lista}."
    )


def mensagem_analista_mpls_obrigatorio_entrada() -> str:
    return _mensagem_analista_mpls_obrigatorio(
        "Para entrar em «Em Configuração do MPLS»,"
    )


def mensagem_analista_mpls_obrigatorio_saida() -> str:
    return _mensagem_analista_mpls_obrigatorio(
        "Para avançar após «Em Configuração do MPLS»,"
    )


def check_analista_mpls_em_config_mpls(
    old_atendimento: Mapping[str, Any],
    old_substatus: str,
    new_substatus: str,
    updates: list | None = None,
) -> Optional[str]:
    """
    Exige analista_mpls ao entrar em «Em Configuração do MPLS» e revalida ao sair para etapa posterior.
    """
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    if not new_substatus or new_substatus == old_substatus:
        return None

    entrada = is_transicao_para_em_config_mpls(old_substatus, new_substatus)
    saida = False
    if old_substatus == "Em Configuração do MPLS":
        idx_old = indice_fluxo_substatus(old_substatus)
        idx_new = indice_fluxo_substatus(new_substatus)
        if idx_old >= 0 and idx_new > idx_old and not is_retorno_de_fila(old_substatus, new_substatus):
            saida = True

    if not entrada and not saida:
        return None

    if not analista_mpls_terceiro_valido(_analista_mpls_efetivo(old_atendimento, updates)):
        if entrada:
            return mensagem_analista_mpls_obrigatorio_entrada()
        return mensagem_analista_mpls_obrigatorio_saida()
    return None


def check_dados_field_triagem_para_fila_aguardando(
    old_atendimento: Mapping[str, Any],
    old_substatus: str,
    new_substatus: str,
    updates: list | None = None,
) -> Optional[str]:
    """Bloqueia Triagem → fila Aguardando sem Contratada, Field e Contato Field."""
    if not is_transicao_triagem_para_fila_aguardando(old_substatus, new_substatus):
        return None
    vazios = dados_field_campos_vazios(old_atendimento, updates)
    if vazios:
        return mensagem_dados_field_obrigatorios_triagem_fila(vazios)
    return None


def resolver_dono_edicao_atendimento(
    atendimento_row: Mapping[str, Any],
) -> tuple[Optional[str], str]:
    """
    Dono só existe em etapas «Em …» (Triagem, Em Config, Em MPLS, Em Caderno).
    Filas «Aguardando Config/MPLS/Caderno» não têm dono — qualquer analista pode assumir.
    """
    sub = (atendimento_row.get("substatus_atendimentos") or "").strip()

    if _substatus_eh_fila_aguardando(sub):
        return None, ""

    if sub in SUBSTATUS_AGUARDA_EXTERNO:
        for etapa in reversed([e for e in FLUXO_SUBSTATUS_ORDEM if e in SUBSTATUS_TO_ANALYST_COL]):
            col = SUBSTATUS_TO_ANALYST_COL[etapa]
            nome = (atendimento_row.get(col) or "").strip()
            if nome:
                return etapa, nome
        return SUBSTATUS_AGUARDA_GESTAO, (atendimento_row.get("analista_atuante_atendimentos") or "").strip()

    if sub not in SUBSTATUS_TO_ANALYST_COL:
        return None, ""

    col = SUBSTATUS_TO_ANALYST_COL[sub]
    return sub, (atendimento_row.get(col) or "").strip()


def mensagem_edicao_apenas_dono(nome_analista: str, etapa: str) -> str:
    return (
        f"Somente o analista '{nome_analista}' pode editar este atendimento "
        f"na etapa '{etapa}'."
    )


def validar_dono_edicao_atendimento(
    current_user_name: str,
    atendimento_row: Mapping[str, Any],
    *,
    is_admin: bool = False,
    is_agendamento_gp: bool = False,
) -> Optional[str]:
    """
    Bloqueia edição por analista que não é dono da etapa «Em …» ativa.
    Filas «Aguardando …» sem dono; AG/GP sem dono em Triagem e Aguardando Config. Remota.
    """
    if is_admin:
        return None

    sub = (atendimento_row.get("substatus_atendimentos") or "").strip()

    if sub in SUBSTATUS_EDICAO_COMPARTILHADA_GESTAO_IMPLANTACAO:
        return None

    if is_agendamento_gp and sub in SUBSTATUS_EDICAO_AGENDAMENTO_GP:
        return None

    if _substatus_eh_fila_aguardando(sub):
        return None

    etapa, dono = resolver_dono_edicao_atendimento(atendimento_row)
    if not etapa:
        return None

    current_user_name = (current_user_name or "").strip()

    if sub in SUBSTATUS_TO_ANALYST_COL and not dono:
        return (
            f"A etapa '{sub}' ainda não foi assumida por um analista. "
            "Altere o substatus para assumir o atendimento antes de editar outros campos."
        )

    if (
        dono
        and current_user_name
        and _normalizar_nome_comparacao(dono) != _normalizar_nome_comparacao(current_user_name)
    ):
        return mensagem_edicao_apenas_dono(dono, etapa)

    return None


def validar_edicao_atendimento(
    user: Mapping[str, Any],
    atendimento_row: Mapping[str, Any],
    hoje: date,
) -> tuple[bool, Optional[str], int]:
    """Permissão de edição: perfil, data, status e dono da etapa ativa."""
    if not atendimento_row:
        return False, "Atendimento não encontrado.", 404

    is_admin = int(user.get("admin_user") or 0) == 1
    if is_admin:
        return True, None, 200

    is_ag_gp = usuario_usa_regras_edicao_gp_agendamento_restritas_dict(user)
    nome_user = (user.get("nome_user") or "").strip()

    status_row = (atendimento_row.get("status_atendimentos") or "").strip()
    substatus = (atendimento_row.get("substatus_atendimentos") or "").strip()
    cmp_date = _data_atendimento_registro(atendimento_row)

    if is_ag_gp:
        if substatus not in SUBSTATUS_EDICAO_AGENDAMENTO_GP:
            return False, mensagem_edicao_restrita_ag_gp(), 403
        if status_row != "Em Atendimento":
            return False, "Edição permitida apenas para atendimentos em andamento.", 403
        if cmp_date != hoje:
            return False, "Edição permitida apenas para atendimentos da data atual.", 403
    else:
        if substatus in SUBSTATUS_EDICAO_SOMENTE_GESTAO:
            return False, mensagem_edicao_apenas_gestao(), 403
        if status_row != "Em Atendimento":
            return False, "Edição permitida apenas para atendimentos em andamento.", 403
        if cmp_date != hoje:
            return False, "Edição permitida apenas para atendimentos da data atual.", 403

    msg_dono = validar_dono_edicao_atendimento(
        nome_user,
        atendimento_row,
        is_admin=False,
        is_agendamento_gp=is_ag_gp,
    )
    if msg_dono:
        return False, msg_dono, 403

    return True, None, 200


def validar_edicao_observacao_atendimento(
    user: Mapping[str, Any],
    atendimento_row: Mapping[str, Any],
    hoje: date,
) -> tuple[bool, Optional[str], int]:
    """
    Grava observações: atendimentos finalizados no dia seguem editáveis
    (ex.: texto obrigatório logo após encerrar com Quebra).
    """
    if not atendimento_row:
        return False, "Atendimento não encontrado.", 404

    if int(user.get("admin_user") or 0) == 1:
        return True, None, 200

    status_row = (atendimento_row.get("status_atendimentos") or "").strip()
    cmp_date = _data_atendimento_registro(atendimento_row)
    if cmp_date != hoje:
        return False, "Edição permitida apenas para atendimentos da data atual.", 403

    if status_row in FINAL_STATUSES_ATENDIMENTO:
        return True, None, 200

    return validar_edicao_atendimento(user, atendimento_row, hoje)


def indice_fluxo_substatus(nome: str) -> int:
    try:
        return FLUXO_SUBSTATUS_ORDEM.index(normalizar_substatus_fluxo(nome))
    except ValueError:
        return -1


def is_retorno_de_fila(old_substatus: str, new_substatus: str) -> bool:
    """
    Retrocesso no fluxo operacional (Triagem → … → Em Caderno).

    Inclui retorno de filas «Aguardando …» e de etapas «Em …» para Triagem
    ou filas anteriores — sem exigir conflito com analista já gravado na etapa destino.
    """
    idx_old = indice_fluxo_substatus(old_substatus)
    idx_new = indice_fluxo_substatus(new_substatus)
    return idx_old >= 0 and idx_new >= 0 and idx_new < idx_old


_PRODESP_ETAPAS_LIBERACAO_ANALISTA: tuple[dict[str, Any], ...] = (
    {
        "fila_substatuses": frozenset({SUBSTATUS_AGUARDA_GESTAO}),
        "col": "analista_atuante_atendimentos",
        "flow_idx": 0,
    },
    {
        "fila_substatuses": frozenset({"Aguardando Config. Remota"}),
        "col": "analista_configuracao_atendimentos",
        "flow_idx": 2,
    },
    {
        "fila_substatuses": frozenset({"Aguardando Config. MPLS"}),
        "col": "analista_mpls_atendimentos",
        "flow_idx": 4,
    },
    {
        "fila_substatuses": frozenset({"Aguardando Caderno de Teste"}),
        "col": "analista_caderno_teste_atendimentos",
        "flow_idx": 6,
    },
)


def colunas_analista_liberar_substatus_transicao(
    old_substatus: str,
    new_substatus: str,
) -> dict[str, str]:
    """
    Ao entrar em fila «Aguardando …» / Aguarda Gestão ou retroceder no fluxo,
    zera o analista da etapa correspondente (espelha prodespProcessarLiberacaoAnalistas).
    """
    old_norm = normalizar_substatus_fluxo((old_substatus or "").strip())
    new_norm = normalizar_substatus_fluxo((new_substatus or "").strip())
    if not new_norm or old_norm == new_norm:
        return {}

    new_idx = indice_fluxo_substatus(new_norm)
    old_idx = indice_fluxo_substatus(old_norm)
    clears: dict[str, str] = {}

    for etapa in _PRODESP_ETAPAS_LIBERACAO_ANALISTA:
        entrou_fila = new_norm in etapa["fila_substatuses"]
        retrocedeu = (
            new_idx >= 0
            and old_idx >= 0
            and new_idx < old_idx
            and etapa["flow_idx"] > new_idx
        )
        if entrou_fila or retrocedeu:
            clears[etapa["col"]] = ""

    return clears


def mensagem_conflito_analista_etapa(nome_analista: str, etapa: str) -> str:
    return (
        f"Atenção: O analista '{nome_analista}' já assumiu este atendimento na etapa '{etapa}'. "
        "Sua alteração foi cancelada para evitar duplicidade."
    )


def check_substatus_change_conflict(
    old_atendimento: Mapping[str, Any],
    old_substatus: str,
    new_substatus: str,
    current_user_name: str,
    *,
    is_admin: bool = False,
    is_agendamento_gp: bool = False,
    em_atendimento: bool = True,
) -> Optional[str]:
    """
    Retorna mensagem de conflito (409) ou None se a mudança de substatus é permitida.
    """
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    if not new_substatus or new_substatus == old_substatus:
        return None

    privilegio_sem_concorrencia = is_admin or (
        is_agendamento_gp and is_substatus_gestao(old_substatus)
    )
    if not em_atendimento or privilegio_sem_concorrencia:
        return None
    if is_retorno_de_fila(old_substatus, new_substatus):
        return None

    if old_substatus in SUBSTATUS_TO_ANALYST_COL:
        col_atual = SUBSTATUS_TO_ANALYST_COL[old_substatus]
        dono_atual = (old_atendimento.get(col_atual) or "").strip()
        if dono_atual and dono_atual != current_user_name:
            return mensagem_conflito_analista_etapa(dono_atual, old_substatus)

    if new_substatus in SUBSTATUS_TO_ANALYST_COL:
        col_nova = SUBSTATUS_TO_ANALYST_COL[new_substatus]
        dono_nova = (old_atendimento.get(col_nova) or "").strip()
        if dono_nova and dono_nova != current_user_name:
            return mensagem_conflito_analista_etapa(dono_nova, new_substatus)

    return None


def analista_coluna_para_substatus(substatus: str) -> Optional[str]:
    return SUBSTATUS_TO_ANALYST_COL.get((substatus or "").strip())


def substatus_solicitado_em_updates(updates: list) -> Optional[str]:
    for item in updates or []:
        if (item.get("coluna") or "").strip() == "substatus":
            val = item.get("valor")
            return (str(val).strip() if val is not None else "") or None
    return None


def update_envolve_substatus_ou_analista(updates: list) -> bool:
    return any(
        (item.get("coluna") or "").strip() in UPDATE_SUBSTATUS_ANALYST_JS_FIELDS
        for item in (updates or [])
    )


def _dono_etapa_ativa(
    atendimento_row: Mapping[str, Any],
    substatus: str,
) -> str:
    col = SUBSTATUS_TO_ANALYST_COL.get((substatus or "").strip())
    if not col:
        return ""
    return (atendimento_row.get(col) or "").strip()


def _check_tentativa_assumir_etapa_ativa(
    old_atendimento: Mapping[str, Any],
    substatus_etapa: str,
    current_user_name: str,
) -> Optional[str]:
    """Etapa «Em…» já ativa e atribuída a outro analista."""
    substatus_etapa = (substatus_etapa or "").strip()
    if substatus_etapa not in SUBSTATUS_TO_ANALYST_COL:
        return None
    dono = _dono_etapa_ativa(old_atendimento, substatus_etapa)
    if dono and dono != current_user_name:
        return mensagem_conflito_analista_etapa(dono, substatus_etapa)
    return None


def _check_analyst_fields_update_conflict(
    old_atendimento: Mapping[str, Any],
    updates: list,
    current_user_name: str,
) -> Optional[str]:
    """Impede sobrescrever analista de etapa ativa ou alterar etapa ativa sem ser o dono."""
    old_sub = (old_atendimento.get("substatus_atendimentos") or "").strip()

    if old_sub in SUBSTATUS_TO_ANALYST_COL:
        msg = _check_tentativa_assumir_etapa_ativa(old_atendimento, old_sub, current_user_name)
        if msg:
            for item in updates or []:
                coluna = (item.get("coluna") or "").strip()
                if coluna == "substatus":
                    return msg
                if coluna in JS_ANALYST_FIELD_TO_ACTIVE_SUBSTATUS:
                    etapa = JS_ANALYST_FIELD_TO_ACTIVE_SUBSTATUS[coluna]
                    if etapa == old_sub:
                        return msg

    for item in updates or []:
        coluna = (item.get("coluna") or "").strip()
        etapa = JS_ANALYST_FIELD_TO_ACTIVE_SUBSTATUS.get(coluna)
        if not etapa:
            continue
        dono = _dono_etapa_ativa(old_atendimento, etapa)
        novo_valor = (str(item.get("valor") or "")).strip()
        if dono and dono != current_user_name and novo_valor and novo_valor != dono:
            return mensagem_conflito_analista_etapa(dono, etapa)

    return None


def check_atendimento_substatus_update(
    old_atendimento: Mapping[str, Any],
    updates: list,
    current_user_name: str,
    *,
    is_admin: bool = False,
    is_agendamento_gp: bool = False,
) -> Optional[str]:
    """
    Valida assumir etapa / mudar substatus, incluindo UI stale e corrida entre analistas.
    Retorna mensagem 409 ou None.
    """
    status_row = (old_atendimento.get("status_atendimentos") or "").strip()
    if status_row != "Em Atendimento":
        return None

    old_sub = (old_atendimento.get("substatus_atendimentos") or "").strip()
    requested = substatus_solicitado_em_updates(updates)

    if is_admin:
        return None

    if is_agendamento_gp and requested and requested != old_sub:
        msg_ag = validar_transicao_substatus_ag_gp(old_sub, requested)
        if msg_ag:
            return msg_ag

    if is_agendamento_gp and is_substatus_gestao(old_sub):
        return None

    if requested:
        if is_retorno_de_fila(old_sub, requested):
            return None

        if requested != old_sub:
            return check_substatus_change_conflict(
                old_atendimento,
                old_sub,
                requested,
                current_user_name,
                is_admin=False,
                is_agendamento_gp=False,
                em_atendimento=True,
            )

        # UI stale: cliente reenvia substatus «Em…» já gravado por outro analista
        msg = _check_tentativa_assumir_etapa_ativa(old_atendimento, requested, current_user_name)
        if msg:
            return msg

    return _check_analyst_fields_update_conflict(old_atendimento, updates, current_user_name)


def is_entrada_aguarda_gestao(old_substatus: str, new_substatus: str) -> bool:
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    return is_substatus_gestao(new_substatus) and not is_substatus_gestao(old_substatus)


def is_saida_aguarda_gestao(old_substatus: str, new_substatus: str) -> bool:
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    if new_substatus in SUBSTATUS_AGUARDA_EXTERNO:
        return False
    return is_substatus_gestao(old_substatus) and not is_substatus_gestao(new_substatus)


def is_entrada_aguarda_externo(old_substatus: str, new_substatus: str) -> bool:
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    return new_substatus in SUBSTATUS_AGUARDA_EXTERNO and new_substatus != old_substatus


def is_saida_em_config_remota(old_substatus: str, new_substatus: str) -> bool:
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    return old_substatus == "Em Configuração Remota" and new_substatus != old_substatus


def _hostname_efetivo_unidade(
    old_unidade: Mapping[str, Any],
    unidade_updates: Mapping[str, Any] | None,
) -> str:
    unidade_updates = unidade_updates or {}
    if "hostname_unidades" in unidade_updates:
        return (unidade_updates.get("hostname_unidades") or "").strip()
    return (old_unidade.get("hostname_unidades") or "").strip()


def check_hostname_obrigatorio_transicao(
    old_unidade: Mapping[str, Any],
    old_substatus: str,
    new_substatus: str,
    unidade_updates: Mapping[str, Any] | None,
    old_status: str | None,
    new_status: str | None,
    *,
    substatus_mudou: bool,
) -> Optional[str]:
    """Exige hostname ao sair de «Em Configuração Remota» ou ao concluir o atendimento."""
    precisa = False
    if substatus_mudou and is_saida_em_config_remota(old_substatus, new_substatus):
        precisa = True
    status_novo = (new_status or "").strip()
    status_antigo = (old_status or "").strip()
    if status_novo == "Concluído" and status_antigo != "Concluído":
        precisa = True
    if not precisa:
        return None
    if not _hostname_efetivo_unidade(old_unidade, unidade_updates):
        return (
            "O campo Hostname é obrigatório para sair de «Em Configuração Remota» "
            "e para concluir o atendimento."
        )
    return None


def is_entrada_com_suporte(old_substatus: str, new_substatus: str) -> bool:
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    return new_substatus == SUBSTATUS_COM_SUPORTE and old_substatus != SUBSTATUS_COM_SUPORTE


def is_saida_com_suporte(old_substatus: str, new_substatus: str) -> bool:
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    return old_substatus == SUBSTATUS_COM_SUPORTE and new_substatus != SUBSTATUS_COM_SUPORTE


def observacoes_transicao_explicitas_no_request(
    transicao_obs: list | None,
) -> list[dict[str, Any]]:
    """
    Observações de transição enviadas explicitamente no POST (transicao_observacoes).
    Não reutiliza histórico do banco — evita regravar obs órfãs ou duplicar em retentativas.
    """
    itens: list[dict[str, Any]] = []
    for obs in transicao_obs or []:
        if not isinstance(obs, dict):
            continue
        texto = (obs.get("observacao_prodesp") or obs.get("observacao") or "").strip()
        if not texto:
            continue
        itens.append(
            {
                "observacao_prodesp": texto,
                "data_observacao": obs.get("data_observacao"),
            }
        )
    return itens


def observacao_quebra_encerramento_explicita(
    payload: Any,
) -> Optional[dict[str, Any]]:
    """Observação «[Substatus Quebra] texto» enviada explicitamente no POST de encerramento."""
    if not isinstance(payload, dict):
        return None
    texto = (payload.get("observacao_prodesp") or payload.get("observacao") or "").strip()
    if not texto:
        return None
    return {
        "observacao_prodesp": texto,
        "data_observacao": payload.get("data_observacao"),
    }


def check_observacao_quebra_encerramento(
    substatus: str,
    observacao: Mapping[str, Any] | None,
) -> Optional[str]:
    """Valida prefixo «[substatus]» e tamanho mínimo do motivo da Quebra."""
    if not observacao:
        return None
    sub = (substatus or "").strip()
    texto = (observacao.get("observacao_prodesp") or "").strip()
    if not texto:
        return None
    prefix = f"[{sub}]"
    if not texto.startswith(prefix):
        return f"A observação de Quebra deve iniciar com «{prefix}»."
    corpo = texto[len(prefix) :].strip().lstrip(":-").strip()
    if len(corpo) < QUEBRA_ENCERRAMENTO_MIN_CHARS:
        return (
            f"Informe o motivo da Quebra com pelo menos "
            f"{QUEBRA_ENCERRAMENTO_MIN_CHARS} caracteres."
        )
    return None


def observacoes_payload_para_validacao_transicao(
    cursor,
    id_atendimento: int,
    transicao_obs: list | None,
) -> list | None:
    """
    Payload para check_observacao_substatus_transicao: usa o enviado no POST ou,
    se vazio, observações já gravadas no atendimento (retentativa após obs órfã legada).
    """
    if transicao_obs:
        return transicao_obs
    if not id_atendimento or cursor is None:
        return transicao_obs
    cursor.execute(
        """
        SELECT observacoes AS observacao_prodesp
        FROM observacoes
        WHERE id_atendimentos_observacoes = %s
        ORDER BY timestamp_observacoes DESC
        LIMIT 30
        """,
        (id_atendimento,),
    )
    rows = cursor.fetchall() or []
    if not rows:
        return transicao_obs
    return [
        {"observacao_prodesp": (r.get("observacao_prodesp") if isinstance(r, dict) else r[0]) or ""}
        for r in rows
    ]


def resolver_regra_observacao_substatus_transicao(
    old_substatus: str,
    new_substatus: str,
) -> Optional[dict[str, Any]]:
    """
    Regra única de observação por transição de substatus (prioridade fixa, sem conflito).
    Retorna dict com regra, prefixo, min_chars ou None se não exige observação.
    """
    old_substatus = (old_substatus or "").strip()
    new_substatus = (new_substatus or "").strip()
    if not new_substatus or new_substatus == old_substatus:
        return None

    if is_entrada_aguarda_gestao(old_substatus, new_substatus):
        return {
            "regra": "entrada_gestao",
            "prefixo": f"[{SUBSTATUS_AGUARDA_GESTAO}]",
            "min_chars": AGUARDA_GESTAO_MIN_CHARS,
        }
    if is_retorno_de_fila(old_substatus, new_substatus):
        return {
            "regra": "retorno_fila",
            "prefixo": f"[Retorno] {old_substatus} → {new_substatus}:",
            "min_chars": RETORNO_SUBSTATUS_MIN_CHARS,
        }
    if is_entrada_com_suporte(old_substatus, new_substatus):
        return {
            "regra": "entrada_com_suporte",
            "prefixo": "[Com Suporte - entrada]",
            "min_chars": COM_SUPORTE_MIN_CHARS,
        }
    if is_entrada_aguarda_externo(old_substatus, new_substatus):
        return {
            "regra": "entrada_aguarda_externo",
            "prefixo": f"[{new_substatus}]",
            "min_chars": AGUARDA_EXTERNO_MIN_CHARS,
        }
    if is_saida_com_suporte(old_substatus, new_substatus):
        return {
            "regra": "saida_com_suporte",
            "prefixo": "[Com Suporte - saída]",
            "min_chars": COM_SUPORTE_MIN_CHARS,
        }
    if is_saida_aguarda_gestao(old_substatus, new_substatus):
        return {
            "regra": "saida_gestao",
            "prefixo": f"[{SUBSTATUS_AGUARDA_GESTAO} - saída]",
            "min_chars": AGUARDA_GESTAO_MIN_CHARS,
        }
    return None


def substatus_paralelo_exige_obs_saida(old_substatus: str) -> bool:
    """Aguarda Gestão/Triagem ou Com Suporte exigem observação de saída ao mudar de substatus."""
    old = (old_substatus or "").strip()
    return is_substatus_gestao(old) or old == SUBSTATUS_COM_SUPORTE


def check_observacao_substatus_transicao(
    old_substatus: str,
    new_substatus: str,
    observacoes_novas: list | None,
) -> Optional[str]:
    """
    Exige observação em retorno de substatus, Aguarda Gestão (entrada/saída) e Com Suporte (entrada/saída).
    Retorna mensagem de erro ou None.
    """
    regra = resolver_regra_observacao_substatus_transicao(old_substatus, new_substatus)
    if not regra:
        return None

    textos = _texto_observacoes_novas(observacoes_novas)
    prefixo = regra["prefixo"]
    min_chars = regra["min_chars"]
    if _observacao_atende_minimo(textos, prefixo, min_chars):
        return None

    regra_id = regra["regra"]
    if regra_id == "entrada_gestao":
        return (
            f"Ao selecionar «{SUBSTATUS_AGUARDA_GESTAO}», informe uma observação "
            f"de pelo menos {min_chars} caracteres."
        )
    if regra_id == "retorno_fila":
        old_s = (old_substatus or "").strip()
        new_s = (new_substatus or "").strip()
        return (
            f"Para voltar o substatus de «{old_s}» para «{new_s}», "
            f"adicione uma observação de pelo menos {min_chars} caracteres."
        )
    if regra_id == "entrada_com_suporte":
        return (
            f"Ao selecionar «{SUBSTATUS_COM_SUPORTE}», informe uma observação "
            f"de pelo menos {min_chars} caracteres."
        )
    if regra_id == "entrada_aguarda_externo":
        dest = (new_substatus or "").strip()
        return (
            f"Ao selecionar «{dest}», informe uma observação "
            f"de pelo menos {min_chars} caracteres."
        )
    if regra_id == "saida_com_suporte":
        return (
            f"Ao sair de «{SUBSTATUS_COM_SUPORTE}», informe uma observação "
            f"de pelo menos {min_chars} caracteres."
        )
    if regra_id == "saida_gestao":
        return (
            f"Ao sair de «{SUBSTATUS_AGUARDA_GESTAO}», informe uma observação "
            f"de pelo menos {min_chars} caracteres."
        )
    return None


def deve_registrar_analista_agendamento_gestao(
    old_substatus: str,
    new_substatus: str,
    *,
    is_agendamento_gp: bool,
) -> bool:
    """Persiste último analista AG/GP ao trabalhar em Aguarda Gestão (não em retorno de fila)."""
    if not is_agendamento_gp:
        return False
    if is_retorno_de_fila(old_substatus, new_substatus):
        return False
    if is_substatus_gestao(new_substatus):
        return True
    if is_substatus_gestao(old_substatus) and not is_substatus_gestao(new_substatus):
        return True
    return False


def avaliar_verificar_id_vgr(
    *,
    status: str,
    substatus: str,
    attendance_date: Optional[date],
    hoje: date,
) -> str:
    """
    action_type esperado pelo front: redirect_edit | block_creation | warn_and_continue | allow
    """
    status = (status or "").strip()
    substatus = (substatus or "").strip()
    if status == "Em Atendimento" and attendance_date == hoje:
        return "redirect_edit"
    if status.lower() in ("concluído", "concluido") and substatus.lower() in ("concluído", "concluido"):
        return "block_creation"
    if attendance_date:
        return "warn_and_continue"
    return "allow"


def mensagem_create_duplicado_em_atendimento(
    atendimento_id: int,
    *,
    analista: str = "",
    substatus: str = "",
) -> str:
    analista_txt = analista.strip() or "—"
    substatus_txt = substatus.strip() or "—"
    return (
        f"Este agendamento já foi iniciado por outro usuário "
        f"(ID: {atendimento_id}, analista: {analista_txt}, substatus: {substatus_txt}). "
        "Você será redirecionado para o atendimento em andamento."
    )


def avaliar_create_atendimento_duplicado(
    *,
    novo_status: str,
    atendimento_existente: Mapping[str, Any] | None,
    hoje: date,
) -> tuple[bool, Optional[str], Optional[int]]:
    """
    Impede criar outro atendimento «Em Atendimento» no mesmo dia para a mesma unidade.
    Retorna (permitido, mensagem, id_atendimento_para_redirect).
    """
    if (novo_status or "").strip() != "Em Atendimento" or not atendimento_existente:
        return True, None, None

    status_existente = (atendimento_existente.get("status_atendimentos") or "").strip()
    data_existente = _data_atendimento_registro(atendimento_existente)
    att_id = atendimento_existente.get("id_atendimentos")

    if status_existente == "Em Atendimento" and data_existente == hoje and att_id:
        msg = mensagem_create_duplicado_em_atendimento(
            int(att_id),
            analista=(atendimento_existente.get("analista_atuante_atendimentos") or ""),
            substatus=(atendimento_existente.get("substatus_atendimentos") or ""),
        )
        return False, msg, int(att_id)

    return True, None, None
