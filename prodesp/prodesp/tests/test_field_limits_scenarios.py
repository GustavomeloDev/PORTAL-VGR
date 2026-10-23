"""Cenários simulados (limites de campo + regras de negócio PRODESP).

Rodar (na raiz do repo, venv ``.venv_portal_pessoal``):

    .venv_portal_pessoal\\Scripts\\python.exe -m prodesp.prodesp.tests.test_field_limits_scenarios

Regressão ícone «editar» na fila: ``test_edicao_payload_lista_api`` — payload como
``/prodesp/api/atendimentos_list`` (com analistas) vs objeto parcial do render antigo.

Estrutura do pacote: ``prodesp/prodesp/README.md``.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

# prodesp/prodesp/tests → raiz do módulo PRODESP (static/, templates/)
_PRODESP_ROOT = Path(__file__).resolve().parents[2]

from prodesp.prodesp.atendimento_business_rules import (
    AGUARDA_EXTERNO_MIN_CHARS,
    AGUARDA_GESTAO_MIN_CHARS,
    COM_SUPORTE_MIN_CHARS,
    RETORNO_SUBSTATUS_MIN_CHARS,
    SUBSTATUS_AGUARDA_CONTRATADA,
    SUBSTATUS_AGUARDA_GESTAO,
    SUBSTATUS_AGUARDANDO_CLIENTE,
    SUBSTATUS_COM_SUPORTE,
    SUBSTATUS_INICIAL_FILA,
    avaliar_create_atendimento_duplicado,
    avaliar_verificar_id_vgr,
    check_analista_mpls_em_config_mpls,
    check_atendimento_substatus_update,
    check_dados_field_create_em_atendimento,
    check_dados_field_triagem_para_fila_aguardando,
    check_observacao_substatus_transicao,
    check_substatus_change_conflict,
    dados_field_campos_vazios,
    dados_field_vazios_do_payload_create,
    deve_registrar_analista_agendamento_gestao,
    is_retorno_de_fila,
    is_substatus_gestao,
    is_transicao_triagem_para_fila_aguardando,
    resolver_dono_edicao_atendimento,
    row_api_para_validacao_edicao,
    update_envolve_substatus_ou_analista,
    validar_dono_edicao_atendimento,
    validar_edicao_atendimento,
    validar_edicao_observacao_atendimento,
    validar_substatus_create_ag_gp,
    validar_transicao_substatus_ag_gp,
)
from prodesp.prodesp.db_field_limits import (
    COLUMN_LIMITS,
    FORM_ELEMENT_LIMITS,
    LOGS_ATENDIMENTOS_MAX,
    LOG_UI_MAX,
    OBSERVACAO_UI_MAX,
    UNIDADES_MV_OPCIONAIS_SPEC,
    UPDATE_JS_TO_DB,
    audit_limits_against_schema,
    audit_mv_opcionais_spec,
    fetch_schema_varchar_limits,
    message_from_mysql_exception,
    normalize_estado_unidade,
    sanitize_plain_ipv4_field,
    unidades_mv_opcionais_update_js_to_db,
    validate_coordinate_text,
    validate_create_payload,
    validate_equipamento_fields,
    validate_estado_unidade,
    validate_link_fields,
    validate_observacao_text,
    validate_update_field,
)

FAILURES: list[str] = []
OK: list[str] = []
HOJE = date(2026, 5, 19)


def check(name: str, got, expect_fail: bool, expect_substr: str | None = None):
    failed = got is not None
    if failed != expect_fail:
        FAILURES.append(f"{name}: esperava fail={expect_fail}, got={got!r}")
        return
    if expect_substr and got and expect_substr not in got:
        FAILURES.append(f"{name}: mensagem sem «{expect_substr}»: {got!r}")
        return
    OK.append(name)


def check_bool(name: str, got: bool, expected: bool):
    if got != expected:
        FAILURES.append(f"{name}: esperava {expected}, got {got}")
    else:
        OK.append(name)


def check_eq(name: str, got, expected):
    if got != expected:
        FAILURES.append(f"{name}: esperava {expected!r}, got {got!r}")
    else:
        OK.append(name)


def check_perm(name: str, user, row, hoje, expect_ok: bool, expect_substr: str | None = None):
    ok, msg, _code = validar_edicao_atendimento(user, row, hoje)
    if ok != expect_ok:
        FAILURES.append(f"{name}: esperava ok={expect_ok}, got ok={ok} msg={msg!r}")
        return
    if expect_substr and msg and expect_substr not in msg:
        FAILURES.append(f"{name}: mensagem sem «{expect_substr}»: {msg!r}")
        return
    OK.append(name)


def _row(**kwargs):
    base = {
        "status_atendimentos": "Em Atendimento",
        "substatus_atendimentos": "Triagem",
        "data_atendimentos": HOJE,
        "analista_atuante_atendimentos": "Ana Silva",
    }
    base.update(kwargs)
    return base


def test_field_limits():
    check(
        "telefone no campo Número",
        validate_update_field("numero", "(12) 99729-8475"),
        True,
        "Número",
    )
    check("número válido curto", validate_update_field("numero", "1435"), False, None)
    check(
        "número 11 dígitos",
        validate_update_field("numero", "12345678901"),
        True,
        "10",
    )
    check(
        "observação acima do TEXT do banco",
        validate_observacao_text("x" * 65536),
        True,
        "Observação",
    )
    check(
        "endereco acima do varchar(90)",
        validate_update_field("endereco", "x" * 91),
        True,
        "Endereço",
    )
    check(
        "field acima do varchar(60)",
        validate_update_field("field", "x" * 61),
        True,
        "Field",
    )
    check(
        "coordenada texto longa",
        validate_coordinate_text("12345678901234"),
        True,
        "Latitude",
    )
    check(
        "serial equipamento longo",
        validate_equipamento_fields({"serial": "S" * 51, "modelo": "FG-40F"}),
        True,
        "Serial",
    )
    check(
        "designador link longo",
        validate_link_fields(
            {
                "designador": "D" * 101,
                "tipo": "MPLS",
                "operadora": "CLARO",
                "velocidade": "100",
                "ip_wan": "10.1.1.1",
                "ip_gateway": "10.1.1.2",
                "ip_mascara": "255.255.255.252",
            }
        ),
        True,
        "Designador",
    )
    check(
        "UF inválida (nome completo)",
        validate_estado_unidade("São Paulo"),
        True,
        "Estado (UF)",
    )
    check("UF válida SP", validate_estado_unidade("sp"), False, None)
    check_eq("normalize UF", normalize_estado_unidade("sp"), "SP")

    check(
        "create payload número longo",
        validate_create_payload({"numero": "1" * 11, "status": "Em Atendimento"}),
        True,
        "Número",
    )
    check(
        "create payload obs unidade longa",
        validate_create_payload(
            {
                "status": "Em Atendimento",
                "new_observacoes": [{"observacao_prodesp": "x" * 65536}],
            }
        ),
        True,
        "Observação",
    )
    check_eq(
        "create payload mv opcional sem ValueError",
        validate_create_payload(
            {
                "status": "Em Atendimento",
                "substatus": "Aguarda Gestão",
                "mv_ip_transito": "10.0.0.1",
            }
        ),
        None,
    )
    check(
        "create payload mv opcional longo",
        validate_create_payload({"mv_ip_transito": "1" * 50}),
        True,
        "Lan Trânsito",
    )

    msg, is_client = message_from_mysql_exception(
        Exception("1406 (22001): Data too long for column 'numero_unidades' at row 1")
    )
    check("mysql 1406 humanizado", msg if is_client else None, True, "Número")

    msg2, is_client2 = message_from_mysql_exception(Exception("2003: Can't connect"))
    if is_client2:
        FAILURES.append("mysql connection: não deveria ser is_client=True")
    elif "suporte" not in msg2.lower() and "tente novamente" not in msg2.lower():
        FAILURES.append(f"mysql genérico: mensagem fraca: {msg2!r}")
    else:
        OK.append("mysql genérico 500")

    if "editAguardandoClienteMotivo" not in FORM_ELEMENT_LIMITS:
        FAILURES.append("lacuna: editAguardandoClienteMotivo sem maxlength")
    else:
        OK.append("aguardando cliente motivo mapeado (edit)")

    if "createAguardandoClienteMotivo" not in FORM_ELEMENT_LIMITS:
        FAILURES.append("lacuna: createAguardandoClienteMotivo sem maxlength")
    else:
        OK.append("aguardando cliente motivo mapeado (create)")

    if UPDATE_JS_TO_DB:
        OK.append("mapa UPDATE_JS cobre campos do update")
        for js_key in ("mv_ip_transito", "mv_rede_voz"):
            loc = UPDATE_JS_TO_DB.get(js_key)
            if not loc or not isinstance(loc, tuple) or len(loc) != 2:
                FAILURES.append(f"UPDATE_JS mv {js_key} deve ser tupla (tabela, coluna)")
            else:
                OK.append(f"UPDATE_JS mv {js_key} tupla ok")

    if FORM_ELEMENT_LIMITS.get("editLogInput") == min(
        COLUMN_LIMITS[("atendimentos", "logs_atendimentos")][0], LOG_UI_MAX
    ):
        OK.append("FORM logs usa min(db, LOG_UI_MAX)")
    else:
        FAILURES.append("lacuna: editLogInput fora de LOG_UI_MAX")

    if LOGS_ATENDIMENTOS_MAX == 16777215:
        OK.append("logs_atendimentos alinhado a MEDIUMTEXT")
    else:
        FAILURES.append(f"logs_atendimentos limite inesperado: {LOGS_ATENDIMENTOS_MAX}")

    if FORM_ELEMENT_LIMITS.get("editObservacaoTexto") == OBSERVACAO_UI_MAX:
        OK.append("FORM observacao usa OBSERVACAO_UI_MAX")
    else:
        FAILURES.append("lacuna: editObservacaoTexto fora de OBSERVACAO_UI_MAX")


def test_edicao_perfil():
    analista = {
        "admin_user": 0,
        "departamentos": ["IMPLANTAÇÃO"],
        "nome_user": "Carlos Lima",
    }
    admin = {"admin_user": 1, "departamentos": ["TI"], "nome_user": "Admin"}
    ag_gp = {
        "admin_user": 0,
        "departamentos": ["AGENDAMENTO"],
        "nome_user": "GP Um",
    }
    supervisor = {
        "admin_user": 0,
        "departamentos": ["SUPERVISORES"],
        "nome_user": "Super Um",
    }

    check_perm(
        "analista dono em config hoje",
        analista,
        _row(
            substatus_atendimentos="Em Configuração Remota",
            analista_configuracao_atendimentos="Carlos Lima",
        ),
        HOJE,
        True,
    )
    check_perm(
        "impl nao dono em config bloqueado",
        {**analista, "nome_user": "Pedro Impl"},
        _row(
            substatus_atendimentos="Em Configuração Remota",
            analista_configuracao_atendimentos="Carlos Lima",
        ),
        HOJE,
        False,
        "Somente o analista",
    )
    check_perm(
        "analista data passada",
        analista,
        _row(
            data_atendimentos=date(2026, 5, 18),
            substatus_atendimentos="Em Configuração Remota",
            analista_configuracao_atendimentos="Carlos Lima",
        ),
        HOJE,
        False,
        "data atual",
    )
    check_perm(
        "analista status concluído",
        analista,
        _row(
            status_atendimentos="Concluído",
            substatus_atendimentos="Em Configuração Remota",
            analista_configuracao_atendimentos="Carlos Lima",
        ),
        HOJE,
        False,
        "andamento",
    )
    check_perm("admin livre", admin, _row(status_atendimentos="Concluído"), HOJE, True)
    check_perm(
        "AG/GP triagem hoje colaborativo",
        ag_gp,
        _row(substatus_atendimentos="Triagem", analista_atuante_atendimentos="Outro GP"),
        HOJE,
        True,
    )
    check_perm(
        "AG/GP aguardando config sem dono colaborativo",
        ag_gp,
        _row(
            substatus_atendimentos="Aguardando Config. Remota",
            analista_atuante_atendimentos="Outro Analista",
        ),
        HOJE,
        True,
    )
    check_perm(
        "impl assume de aguardando config",
        {**analista, "nome_user": "Pedro Impl"},
        _row(
            substatus_atendimentos="Aguardando Config. Remota",
            analista_atuante_atendimentos="GP Agendamento",
        ),
        HOJE,
        True,
    )
    check_perm(
        "AG/GP aguardando MPLS bloqueado",
        ag_gp,
        _row(
            substatus_atendimentos="Aguardando Config. MPLS",
            analista_mpls_atendimentos="",
        ),
        HOJE,
        False,
        "Aguarda Gestão",
    )
    check_perm(
        "impl aguarda gestao bloqueado",
        analista,
        _row(substatus_atendimentos=SUBSTATUS_AGUARDA_GESTAO),
        HOJE,
        False,
        "exclusivo",
    )
    check_perm(
        "impl aguarda contratada compartilhada",
        {**analista, "nome_user": "Pedro Impl"},
        _row(
            substatus_atendimentos=SUBSTATUS_AGUARDA_CONTRATADA,
            analista_configuracao_atendimentos="Outro Analista",
        ),
        HOJE,
        True,
    )
    check_perm(
        "impl aguarda licenca compartilhada",
        {**analista, "nome_user": "Pedro Impl"},
        _row(
            substatus_atendimentos="Aguarda Licença",
            analista_configuracao_atendimentos="Outro Analista",
        ),
        HOJE,
        True,
    )
    check_perm(
        "impl aguardando cliente compartilhado",
        {**analista, "nome_user": "Pedro Impl"},
        _row(
            substatus_atendimentos=SUBSTATUS_AGUARDANDO_CLIENTE,
            analista_configuracao_atendimentos="Outro Analista",
        ),
        HOJE,
        True,
    )
    check_perm(
        "AG/GP em config remota bloqueado",
        ag_gp,
        _row(substatus_atendimentos="Em Configuração Remota"),
        HOJE,
        False,
        "Aguarda Gestão",
    )
    check_perm(
        "SUPERVISORES triagem hoje colaborativo",
        supervisor,
        _row(substatus_atendimentos="Triagem", analista_atuante_atendimentos="Outro"),
        HOJE,
        True,
    )
    check_perm(
        "impl com GP extra usa regras de implantador",
        {
            "admin_user": 0,
            "departamentos": ["IMPLANTAÇÃO", "GP"],
            "nome_user": "Híbrido",
        },
        _row(
            substatus_atendimentos="Em Configuração Remota",
            analista_configuracao_atendimentos="Híbrido",
        ),
        HOJE,
        True,
    )


def test_edicao_observacao_pos_quebra_ag_gp():
    ag_gp = {
        "admin_user": 0,
        "departamentos": ["AGENDAMENTO"],
        "nome_user": "GP Um",
    }
    row_quebra = _row(
        status_atendimentos="Quebra",
        substatus_atendimentos="Quebra Link",
        data_atendimentos=HOJE,
    )
    ok, msg, code = validar_edicao_atendimento(ag_gp, row_quebra, HOJE)
    check_bool("AG/GP update bloqueado após Quebra", ok, False)
    ok_obs, msg_obs, code_obs = validar_edicao_observacao_atendimento(
        ag_gp, row_quebra, HOJE
    )
    check_bool("AG/GP observação pós-Quebra no dia permitida", ok_obs, True)
    check_eq("obs pós-Quebra sem msg", msg_obs, None)


def test_edicao_payload_lista_api():
    """
    Regressão: permissão na grade usa linha completa da API (analista_configuracao, etc.).
    Objeto parcial (só status/substatus/data) reproduz o bug do lápis ausente.
    """
    diego = {
        "admin_user": 0,
        "departamento_user": "IMPLANTAÇÃO",
        "departamentos_extras": [],
        "nome_user": "Diego Lima Dos Santos",
    }
    row_lista = {
        "status_atendimento": "Em Atendimento",
        "substatus_atendimento": "Em Configuração Remota",
        "data_atendimento": HOJE.isoformat(),
        "analista_atuante": "Sandra Pereira Da Silva",
        "analista_configuracao": "Diego Lima Dos Santos",
    }
    row_mapeada = row_api_para_validacao_edicao(row_lista)

    check_perm(
        "lista API dono em config (regressao icone editar)",
        diego,
        row_mapeada,
        HOJE,
        True,
    )
    etapa, dono = resolver_dono_edicao_atendimento(row_mapeada)
    check_eq("lista API resolver etapa", etapa, "Em Configuração Remota")
    check_eq("lista API resolver dono", dono, "Diego Lima Dos Santos")

    row_parcial = {
        "status_atendimento": "Em Atendimento",
        "substatus_atendimento": "Em Configuração Remota",
        "data_atendimento": HOJE.isoformat(),
    }
    check_perm(
        "lista API parcial sem analista bloqueia (anti-padrao render)",
        diego,
        row_api_para_validacao_edicao(row_parcial),
        HOJE,
        False,
        "assumida",
    )

    impl_gp = {
        "admin_user": 0,
        "departamento_user": "IMPLANTAÇÃO",
        "departamentos_extras": ["GP"],
        "nome_user": "Diego Lima Dos Santos",
    }
    check_perm(
        "IMPLANTACAO+GP dono em config prevalece implantacao",
        impl_gp,
        row_mapeada,
        HOJE,
        True,
    )


def test_concorrencia_substatus():
    base = _row(
        substatus_atendimentos="Triagem",
        analista_atuante_atendimentos="Carlos Lima",
    )

    # Segundo analista tenta mudar Triagem → Em Config Remota
    msg = check_substatus_change_conflict(
        base,
        "Triagem",
        "Em Configuração Remota",
        "Maria Souza",
        em_atendimento=True,
    )
    check("2 analistas mesma etapa Triagem", msg, True, "Carlos Lima")

    # Dono da etapa pode avançar
    check(
        "dono Triagem avança",
        check_substatus_change_conflict(
            base,
            "Triagem",
            "Em Configuração Remota",
            "Carlos Lima",
            em_atendimento=True,
        ),
        False,
        None,
    )

    # Dois GP em Triagem — sem conflito (privilégio AG/GP)
    check(
        "2 GP em Triagem sem conflito",
        check_substatus_change_conflict(
            base,
            "Triagem",
            "Aguardando Config. Remota",
            "GP Dois",
            is_agendamento_gp=True,
            em_atendimento=True,
        ),
        False,
        None,
    )

    # Retorno de fila: Aguardando Config → Triagem
    check_bool(
        "retorno fila Aguardando Config para Triagem",
        is_retorno_de_fila("Aguardando Config. Remota", "Triagem"),
        True,
    )
    check_bool(
        "retorno Em Config para Triagem (IMPLANTACAO)",
        is_retorno_de_fila("Em Configuração Remota", "Triagem"),
        True,
    )
    check(
        "retorno fila sem conflito mesmo com dono",
        check_substatus_change_conflict(
            _row(
                substatus_atendimentos="Aguardando Config. Remota",
                analista_atuante_atendimentos="Carlos Lima",
            ),
            "Aguardando Config. Remota",
            "Triagem",
            "Maria Souza",
            em_atendimento=True,
        ),
        False,
        None,
    )
    check(
        "retorno Em Config para Triagem sem conflito analista triagem",
        check_substatus_change_conflict(
            _row(
                substatus_atendimentos="Em Configuração Remota",
                analista_atuante_atendimentos="Carlos Lima",
                analista_configuracao_atendimentos="Maria Souza",
            ),
            "Em Configuração Remota",
            "Triagem",
            "Maria Souza",
            em_atendimento=True,
        ),
        False,
        None,
    )

    # Etapa destino já ocupada por outro
    em_config = _row(
        substatus_atendimentos="Aguardando Config. Remota",
        analista_configuracao_atendimentos="João Config",
    )
    check(
        "entrar em etapa já ocupada",
        check_substatus_change_conflict(
            em_config,
            "Aguardando Config. Remota",
            "Em Configuração Remota",
            "Maria Souza",
            em_atendimento=True,
        ),
        True,
        "João Config",
    )

    # Admin ignora concorrência
    check(
        "admin ignora conflito",
        check_substatus_change_conflict(
            base,
            "Triagem",
            "Em Configuração Remota",
            "Admin User",
            is_admin=True,
            em_atendimento=True,
        ),
        False,
        None,
    )


def test_agendados_id_vgr():
    check_eq(
        "agendado em atendimento hoje redirect",
        avaliar_verificar_id_vgr(
            status="Em Atendimento",
            substatus="Triagem",
            attendance_date=HOJE,
            hoje=HOJE,
        ),
        "redirect_edit",
    )
    check_eq(
        "concluido+concluido block",
        avaliar_verificar_id_vgr(
            status="Concluído",
            substatus="Concluído",
            attendance_date=HOJE,
            hoje=HOJE,
        ),
        "block_creation",
    )
    check_eq(
        "atendimento passado warn",
        avaliar_verificar_id_vgr(
            status="Concluído",
            substatus="Quebra",
            attendance_date=date(2026, 5, 1),
            hoje=HOJE,
        ),
        "warn_and_continue",
    )
    check_eq(
        "sem historico allow",
        avaliar_verificar_id_vgr(
            status="",
            substatus="",
            attendance_date=None,
            hoje=HOJE,
        ),
        "allow",
    )


def test_create_duplicado_agendado():
    row_ativo = {
        "id_atendimentos": 501,
        "status_atendimentos": "Em Atendimento",
        "substatus_atendimentos": "Triagem",
        "analista_atuante_atendimentos": "Usuario A",
        "data_atendimentos": HOJE,
    }
    ok, msg, att_id = avaliar_create_atendimento_duplicado(
        novo_status="Em Atendimento",
        atendimento_existente=row_ativo,
        hoje=HOJE,
    )
    check_bool("bloqueia 2o create Em Atendimento hoje", ok, False)
    if att_id != 501:
        FAILURES.append(f"redirect id: esperava 501, got {att_id}")
    elif msg and "Usuario A" in msg and "501" in msg:
        OK.append("mensagem create duplicado clara")

    ok2, _msg2, att2 = avaliar_create_atendimento_duplicado(
        novo_status="Em Atendimento",
        atendimento_existente=None,
        hoje=HOJE,
    )
    check_bool("permite create se nao existe ativo", ok2, True)

    ok3, _msg3, att3 = avaliar_create_atendimento_duplicado(
        novo_status="Concluído",
        atendimento_existente=row_ativo,
        hoje=HOJE,
    )
    check_bool("nao bloqueia status final com ativo (regra separada)", ok3, True)


def _updates(*pairs):
    return [{"coluna": k, "valor": v} for k, v in pairs]


def test_substatus_pickup_stale_e_filas():
    """IMPLANTACAO: assumir fila Aguardando -> Em..., UI stale e corrida."""

    # 1o analista pega Aguardando Config -> Em Config
    row_aguardando = _row(
        substatus_atendimentos="Aguardando Config. Remota",
        analista_configuracao_atendimentos="",
    )
    check(
        "impl 1o assume aguardando config",
        check_atendimento_substatus_update(
            row_aguardando,
            _updates(("substatus", "Em Configuração Remota")),
            "Maria Souza",
        ),
        False,
        None,
    )

    # 2o analista UI stale: DB ja Em Config com dono
    row_em_config = _row(
        substatus_atendimentos="Em Configuração Remota",
        analista_configuracao_atendimentos="Maria Souza",
    )
    check(
        "impl 2o stale em config bloqueado",
        check_atendimento_substatus_update(
            row_em_config,
            _updates(("substatus", "Em Configuração Remota")),
            "Joao Impl",
        ),
        True,
        "Maria Souza",
    )

    # Dono pode reenviar mesmo substatus (auto-save)
    check(
        "dono pode salvar mesmo substatus",
        check_atendimento_substatus_update(
            row_em_config,
            _updates(("substatus", "Em Configuração Remota")),
            "Maria Souza",
        ),
        False,
        None,
    )

    # Aguardando MPLS -> Em MPLS: sem bloqueio por analista_mpls (terceiro, nao dono)
    row_mpls = _row(
        substatus_atendimentos="Aguardando Config. MPLS",
        analista_mpls_atendimentos="Edson Francisco Da Silva",
    )
    check(
        "impl aguardando mpls pode assumir",
        check_atendimento_substatus_update(
            row_mpls,
            _updates(("substatus", "Em Configuração do MPLS")),
            "Pedro Impl",
        ),
        False,
        None,
    )

    # Aguardando Caderno -> Em Caderno
    row_caderno = _row(
        substatus_atendimentos="Aguardando Caderno de Teste",
        analista_caderno_teste_atendimentos="",
    )
    check(
        "impl assume aguardando caderno",
        check_atendimento_substatus_update(
            row_caderno,
            _updates(("substatus", "Em Caderno de Teste")),
            "Lucia Impl",
        ),
        False,
        None,
    )

    # Triagem: B tenta avancar sem ser dono
    row_triagem = _row(
        substatus_atendimentos="Triagem",
        analista_atuante_atendimentos="Carlos Lima",
    )
    check(
        "impl triagem bloqueia nao dono",
        check_atendimento_substatus_update(
            row_triagem,
            _updates(("substatus", "Aguardando Config. Remota")),
            "Pedro Impl",
        ),
        True,
        "Carlos Lima",
    )

    # Tentativa de roubar via campo analista
    check(
        "impl nao sobrescreve analista config",
        check_atendimento_substatus_update(
            row_em_config,
            _updates(("analista_configuracao", "Joao Impl")),
            "Joao Impl",
        ),
        True,
        "Maria Souza",
    )

    # Sem substatus no payload: dono edita field ok
    check(
        "impl sem substatus no payload nao conflita",
        check_atendimento_substatus_update(
            row_em_config,
            _updates(("field", "Field X")),
            "Joao Impl",
        ),
        False,
        None,
    )

    # Retorno fila continua liberado (Aguardando -> etapa anterior)
    row_aguardando_retorno = _row(
        substatus_atendimentos="Aguardando Config. Remota",
        analista_atuante_atendimentos="Carlos Lima",
    )
    check(
        "retorno fila via check_atendimento",
        check_atendimento_substatus_update(
            row_aguardando_retorno,
            _updates(("substatus", "Triagem")),
            "Joao Impl",
        ),
        False,
        None,
    )

    # Dono em Em Config volta para Triagem mesmo com outro analista na triagem
    row_em_config_retorno = _row(
        substatus_atendimentos="Em Configuração Remota",
        analista_atuante_atendimentos="Carlos Lima",
        analista_configuracao_atendimentos="Maria Souza",
    )
    check(
        "retorno Em Config para Triagem sem conflito",
        check_atendimento_substatus_update(
            row_em_config_retorno,
            _updates(("substatus", "Triagem")),
            "Maria Souza",
        ),
        False,
        None,
    )

    # AG/GP Triagem sem conflito
    check(
        "AG/GP triagem check_atendimento",
        check_atendimento_substatus_update(
            row_triagem,
            _updates(("substatus", "Aguardando Config. Remota")),
            "GP Dois",
            is_agendamento_gp=True,
        ),
        False,
        None,
    )

    check_bool(
        "update_envolve detecta substatus",
        update_envolve_substatus_ou_analista(_updates(("substatus", "Triagem"))),
        True,
    )
    check_bool(
        "update_envolve detecta analista config",
        update_envolve_substatus_ou_analista(_updates(("analista_configuracao", "X"))),
        True,
    )
    check_bool(
        "update_envolve ignora field",
        update_envolve_substatus_ou_analista(_updates(("field", "X"))),
        False,
    )


def test_transicao_substatus_ag_gp():
    """AG/GP não avança para etapas «Em …»; só filas Aguardando e pendências paralelas."""
    check(
        "AG/GP Gestão → Aguardando Config permitido",
        validar_transicao_substatus_ag_gp(
            SUBSTATUS_AGUARDA_GESTAO, SUBSTATUS_INICIAL_FILA
        ),
        False,
        None,
    )
    check(
        "AG/GP Gestão → Em Config bloqueado",
        validar_transicao_substatus_ag_gp(
            SUBSTATUS_AGUARDA_GESTAO, "Em Configuração Remota"
        ),
        True,
        "Implantação",
    )
    check(
        "AG/GP Aguardando Config → Em Config bloqueado",
        validar_transicao_substatus_ag_gp(
            SUBSTATUS_INICIAL_FILA, "Em Configuração Remota"
        ),
        True,
        "Implantação",
    )
    check(
        "AG/GP Aguardando Config → Gestão (retorno) permitido",
        validar_transicao_substatus_ag_gp(
            SUBSTATUS_INICIAL_FILA, SUBSTATUS_AGUARDA_GESTAO
        ),
        False,
        None,
    )
    check(
        "AG/GP Aguardando Config → Aguarda Licença permitido",
        validar_transicao_substatus_ag_gp(SUBSTATUS_INICIAL_FILA, "Aguarda Licença"),
        False,
        None,
    )
    check(
        "AG/GP Aguardando Config → Quebra Field permitido",
        validar_transicao_substatus_ag_gp(SUBSTATUS_INICIAL_FILA, "Quebra Field"),
        False,
        None,
    )
    check(
        "AG/GP Aguarda Licença → Gestão permitido",
        validar_transicao_substatus_ag_gp("Aguarda Licença", SUBSTATUS_AGUARDA_GESTAO),
        False,
        None,
    )
    check(
        "AG/GP Aguarda Contratada → Aguardando Config permitido",
        validar_transicao_substatus_ag_gp(
            SUBSTATUS_AGUARDA_CONTRATADA, SUBSTATUS_INICIAL_FILA
        ),
        False,
        None,
    )
    check(
        "AG/GP Aguardando Cliente → Aguardando MPLS bloqueado",
        validar_transicao_substatus_ag_gp(
            SUBSTATUS_AGUARDANDO_CLIENTE, "Aguardando Config. MPLS"
        ),
        True,
        "Implantação",
    )
    check(
        "AG/GP Gestão → Aguardando MPLS bloqueado",
        validar_transicao_substatus_ag_gp(
            SUBSTATUS_AGUARDA_GESTAO, "Aguardando Config. MPLS"
        ),
        True,
        "Implantação",
    )
    check(
        "check_atendimento AG/GP bloqueia Em Config",
        check_atendimento_substatus_update(
            _row(substatus_atendimentos=SUBSTATUS_INICIAL_FILA),
            _updates(("substatus", "Em Configuração Remota")),
            "GP Teste",
            is_agendamento_gp=True,
        ),
        True,
        "Implantação",
    )
    check(
        "create AG/GP nasce em Aguardando Config",
        validar_substatus_create_ag_gp(""),
        False,
        None,
    )
    check(
        "create AG/GP bloqueia Em Config",
        validar_substatus_create_ag_gp("Em Configuração Remota"),
        True,
        "Implantação",
    )
    check(
        "create AG/GP permite Aguarda Licença",
        validar_substatus_create_ag_gp("Aguarda Licença"),
        False,
        None,
    )


def test_dono_edicao_todas_etapas():
    row_config = _row(
        substatus_atendimentos="Em Configuração Remota",
        analista_configuracao_atendimentos="Maria Config",
    )
    etapa, dono = resolver_dono_edicao_atendimento(row_config)
    check_eq("dono em config", dono, "Maria Config")
    check_eq("etapa em config", etapa, "Em Configuração Remota")

    row_ag = _row(
        substatus_atendimentos="Aguardando Config. MPLS",
        analista_configuracao_atendimentos="Maria Config",
    )
    etapa2, dono2 = resolver_dono_edicao_atendimento(row_ag)
    check_eq("aguardando mpls sem dono", dono2, "")
    check_eq("aguardando mpls etapa null", etapa2, None)

    check(
        "validar_dono nao bloqueia impl em mpls",
        validar_dono_edicao_atendimento("Pedro", _row(
            substatus_atendimentos="Em Configuração do MPLS",
            analista_mpls_atendimentos="Edson Francisco Da Silva",
        )),
        False,
        None,
    )

    row_ag_mpls = _row(
        substatus_atendimentos="Aguardando Config. MPLS",
        analista_mpls_atendimentos="",
    )
    check(
        "entrar em mpls sem analista terceiro bloqueia",
        check_analista_mpls_em_config_mpls(
            row_ag_mpls,
            "Aguardando Config. MPLS",
            "Em Configuração do MPLS",
            _updates(("substatus", "Em Configuração do MPLS")),
        ),
        True,
        "entrar em",
    )
    check(
        "entrar em mpls com analista terceiro ok",
        check_analista_mpls_em_config_mpls(
            row_ag_mpls,
            "Aguardando Config. MPLS",
            "Em Configuração do MPLS",
            _updates(
                ("substatus", "Em Configuração do MPLS"),
                ("analista_mpls_atendimentos", "Edson Francisco Da Silva"),
            ),
        ),
        False,
        None,
    )

    row_em_mpls = _row(
        substatus_atendimentos="Em Configuração do MPLS",
        analista_mpls_atendimentos="",
    )
    check(
        "sair em mpls sem analista terceiro bloqueia",
        check_analista_mpls_em_config_mpls(
            row_em_mpls,
            "Em Configuração do MPLS",
            "Aguardando Caderno de Teste",
            _updates(("substatus", "Aguardando Caderno de Teste")),
        ),
        True,
        "analista MPLS",
    )
    check(
        "sair em mpls com analista terceiro ok",
        check_analista_mpls_em_config_mpls(
            row_em_mpls,
            "Em Configuração do MPLS",
            "Aguardando Caderno de Teste",
            _updates(
                ("substatus", "Aguardando Caderno de Teste"),
                ("analista_mpls_atendimentos", "Edson Francisco Da Silva"),
            ),
        ),
        False,
        None,
    )

    check(
        "etapa ativa sem dono bloqueia edicao field",
        validar_dono_edicao_atendimento(
            "Pedro",
            _row(substatus_atendimentos="Em Caderno de Teste"),
        ),
        True,
        "ainda não foi assumida",
    )


def test_coordenadas_equivalentes():
    from prodesp.app import coordenadas_equivalentes

    check_bool(
        "coord 8 vs 7 casas equivalentes",
        coordenadas_equivalentes("-46.41629740", "-46.4162974"),
        True,
    )
    check_bool(
        "coord valores diferentes",
        coordenadas_equivalentes("-46.41629740", "-46.41629750"),
        False,
    )
    check_bool("coord ambos vazios", coordenadas_equivalentes("", None), True)


def test_sanitize_plain_ipv4_field():
    check_bool(
        "plain ipv4 remove espacos",
        sanitize_plain_ipv4_field("10.0.0.1 ") == "10.0.0.1",
        True,
    )
    check_bool(
        "plain ipv4 remove letras",
        sanitize_plain_ipv4_field("10.0.0.x abc") == "10.0.0.",
        True,
    )
    check_bool(
        "plain ipv4 so letras vira vazio",
        sanitize_plain_ipv4_field("abc") == "",
        True,
    )


def test_dados_field_triagem_para_fila():
    check_bool(
        "transicao triagem ag config remota",
        is_transicao_triagem_para_fila_aguardando("Triagem", "Aguardando Config. Remota"),
        True,
    )
    check_bool(
        "triagem para em config nao exige fila",
        is_transicao_triagem_para_fila_aguardando("Triagem", "Em Configuração Remota"),
        False,
    )
    check_bool(
        "triagem para aguardando cliente nao",
        is_transicao_triagem_para_fila_aguardando("Triagem", "Aguardando Cliente"),
        False,
    )
    check_bool(
        "ag config para ag mpls nao",
        is_transicao_triagem_para_fila_aguardando(
            "Aguardando Config. Remota", "Aguardando Config. MPLS"
        ),
        False,
    )

    row_vazio = _row()
    check(
        "triagem fila sem dados field bloqueia",
        check_dados_field_triagem_para_fila_aguardando(
            row_vazio, "Triagem", "Aguardando Config. Remota", []
        ),
        True,
        "Dados Field",
    )
    check_eq(
        "dados field vazios lista 3 campos",
        dados_field_campos_vazios(row_vazio, []),
        ["Contratada", "Field", "Contato Field"],
    )

    row_ok = _row(
        contratada_atendimentos="Contratada X",
        field_atendimentos="Joao Field",
        contato_field_atendimentos="(11) 98765-4321",
    )
    check(
        "triagem fila com dados field ok",
        check_dados_field_triagem_para_fila_aguardando(
            row_ok, "Triagem", "Aguardando Caderno de Teste", []
        ),
        False,
        None,
    )

    updates = [
        {"coluna": "contratada", "valor": "C1"},
        {"coluna": "field", "valor": "F1"},
        {"coluna": "contato_field", "valor": "11988887777"},
    ]
    check(
        "updates preenchem dados field",
        check_dados_field_triagem_para_fila_aguardando(
            row_vazio, "Triagem", "Aguardando Config. MPLS", updates
        ),
        False,
        None,
    )
    check(
        "contato so digitos no payload",
        check_dados_field_triagem_para_fila_aguardando(
            row_vazio,
            "Triagem",
            "Aguardando Config. Remota",
            [
                {"coluna": "contratada", "valor": "C"},
                {"coluna": "field", "valor": "F"},
                {"coluna": "contato_field", "valor": "(11) 9"},
            ],
        ),
        False,
        None,
    )

    check(
        "create em atendimento sem field bloqueia",
        check_dados_field_create_em_atendimento({"status": "Em Atendimento"}),
        True,
        "Dados Field",
    )
    check_eq(
        "create payload field vazios",
        dados_field_vazios_do_payload_create({"status": "Em Atendimento", "contratada": ""}),
        ["Contratada", "Field", "Contato Field"],
    )
    check(
        "create em atendimento com field ok",
        check_dados_field_create_em_atendimento(
            {
                "status": "Em Atendimento",
                "contratada": "Vivo Redes - Interior",
                "field": "Joao",
                "contato_field": "11999998888",
            }
        ),
        False,
        None,
    )
    check(
        "create status final nao usa gate em atendimento",
        check_dados_field_create_em_atendimento({"status": "Quebra"}),
        False,
        None,
    )


def test_kpis_tempo_etapa_dashboard():
    """KPIs executivos de tempo: acesso e agregação sem banco."""
    from types import SimpleNamespace

    from prodesp.app import (
        _prodesp_build_tempos_etapa_kpis_dashboard,
        _prodesp_etapa_tempo_stat,
        _prodesp_pode_ver_kpis_tempo_executivo,
    )

    admin = SimpleNamespace(admin_user=1, nome_user="Qualquer")
    felipe = SimpleNamespace(admin_user=0, nome_user="Felipe Dos Santos Paixão")
    outro = SimpleNamespace(admin_user=0, nome_user="Outro Usuario")

    check_bool("kpi tempo admin", _prodesp_pode_ver_kpis_tempo_executivo(admin), True)
    check_bool("kpi tempo felipe", _prodesp_pode_ver_kpis_tempo_executivo(felipe), True)
    check_bool("kpi tempo outro", _prodesp_pode_ver_kpis_tempo_executivo(outro), False)

    rows = [
        {
            "tempo_triagem": "01:00:00",
            "id_atendimentos": 1,
            "id_vgr": "V1",
            "nome_unidade": "U1",
            "acronimo": "",
            "analista_atuante_atendimentos": "Ana A",
        },
        {
            "tempo_triagem": "03:00:00",
            "id_atendimentos": 2,
            "id_vgr": "V2",
            "id_intragov": "IG99",
            "acronimo": "PCESP",
            "analista_atuante_atendimentos": "Ana B",
        },
        {
            "tempo_triagem": "00:00:00",
            "id_atendimentos": 3,
            "id_vgr": "",
            "nome_unidade": "",
            "acronimo": "ACR",
            "analista_atuante_atendimentos": "",
        },
    ]
    stat = _prodesp_etapa_tempo_stat(
        rows, "tempo_triagem", "analista_atuante_atendimentos"
    )
    check_eq("triagem ocorrencias", stat["ocorrencias"], 2)
    check_eq("triagem media", stat["tempo_medio"], "02:00:00")
    check_eq("triagem maior id", stat["maior_ofensor"]["id_atendimento"], 2)
    check_eq("triagem maior tempo", stat["maior_ofensor"]["tempo"], "03:00:00")
    check_eq("triagem maior acronimo", stat["maior_ofensor"]["acronimo"], "PCESP")
    check_eq("triagem maior intragov", stat["maior_ofensor"]["id_intragov"], "IG99")

    stat_cli = _prodesp_etapa_tempo_stat(
        [
            {
                "tempo_aguardando_cliente": "02:00:00",
                "id_atendimentos": 9,
                "id_vgr": "V9",
                "id_intragov": "IG1",
                "acronimo": "UNI",
                "analista_atuante_atendimentos": "Nao deve aparecer",
            }
        ],
        "tempo_aguardando_cliente",
        None,
    )
    check_bool(
        "aguardando cliente sem analista",
        stat_cli["maior_ofensor"]["analista"] is None,
        True,
    )

    from unittest.mock import MagicMock, patch

    view_rows = [
        {
            "tempo_total_geral": "04:00:00",
            "tempo_total_atendimento": "02:00:00",
            "tempo_aguardando_cliente": "01:00:00",
            "tempo_triagem": "01:00:00",
            "tempo_aguardando_config_remota": "00:00:00",
            "tempo_config_remota": "00:00:00",
            "tempo_aguardando_mpls": "00:00:00",
            "tempo_config_mpls": "00:00:00",
            "tempo_aguardando_caderno": "00:00:00",
            "tempo_caderno_teste": "00:00:00",
            "analista_atuante_atendimentos": "X",
            "analista_configuracao_atendimentos": "",
            "analista_mpls_atendimentos": "",
            "analista_caderno_teste_atendimentos": "",
            "id_atendimentos": 10,
            "id_vgr": "VG",
            "id_intragov": "IG10",
            "acronimo": "UNI",
        }
    ]
    with patch(
        "prodesp.app._prodesp_carregar_tempos_etapa_view",
        return_value=view_rows,
    ):
        payload = _prodesp_build_tempos_etapa_kpis_dashboard(
            MagicMock(), "2025-01-01", "2025-01-31"
        )
    check_eq("resumo total", payload["resumo_ciclo"]["total_atendimentos"], 1)
    check_eq(
        "resumo geral medio",
        payload["resumo_ciclo"]["tempo_total_geral_medio"],
        "04:00:00",
    )
    check_eq(
        "resumo diff espera",
        payload["resumo_ciclo"]["diferenca_espera_media"],
        "02:00:00",
    )
    check_eq("grupos espera count", len(payload["espera"]), 4)
    check_eq("grupos produtivo count", len(payload["produtivo"]), 5)


def test_observacao_substatus_transicao():
    """Retorno, Aguarda Gestão (entrada/saída) e Com Suporte exigem observação com prefixo e tamanho mínimo."""
    retorno_prefix = "[Retorno] Em Configuração Remota → Aguardando Config. Remota:"
    obs_curta = [{"observacao_prodesp": f"{retorno_prefix} curta"}]
    obs_ok = [
        {
            "observacao_prodesp": f"{retorno_prefix} {'x' * RETORNO_SUBSTATUS_MIN_CHARS}"
        }
    ]
    check_bool(
        "retorno sem obs",
        check_observacao_substatus_transicao(
            "Em Configuração Remota",
            SUBSTATUS_INICIAL_FILA,
            None,
        )
        is not None,
        True,
    )
    check_bool(
        "retorno obs curta",
        check_observacao_substatus_transicao(
            "Em Configuração Remota",
            SUBSTATUS_INICIAL_FILA,
            obs_curta,
        )
        is not None,
        True,
    )
    check_eq(
        "retorno obs ok",
        check_observacao_substatus_transicao(
            "Em Configuração Remota",
            SUBSTATUS_INICIAL_FILA,
            obs_ok,
        ),
        None,
    )

    gestao_prefix = f"[{SUBSTATUS_AGUARDA_GESTAO}]"
    check_bool(
        "gestao obs curta",
        check_observacao_substatus_transicao(
            SUBSTATUS_INICIAL_FILA,
            SUBSTATUS_AGUARDA_GESTAO,
            [{"observacao_prodesp": f"{gestao_prefix} curta"}],
        )
        is not None,
        True,
    )
    check_eq(
        "gestao obs ok",
        check_observacao_substatus_transicao(
            SUBSTATUS_INICIAL_FILA,
            SUBSTATUS_AGUARDA_GESTAO,
            [
                {
                    "observacao_prodesp": f"{gestao_prefix} {'g' * AGUARDA_GESTAO_MIN_CHARS}"
                }
            ],
        ),
        None,
    )

    entrada_cs = "[Com Suporte - entrada]"
    saida_cs = "[Com Suporte - saída]"
    texto_cs = "s" * COM_SUPORTE_MIN_CHARS
    check_eq(
        "com suporte entrada ok",
        check_observacao_substatus_transicao(
            SUBSTATUS_INICIAL_FILA,
            SUBSTATUS_COM_SUPORTE,
            [{"observacao_prodesp": f"{entrada_cs} {texto_cs}"}],
        ),
        None,
    )
    check_eq(
        "com suporte saida ok",
        check_observacao_substatus_transicao(
            SUBSTATUS_COM_SUPORTE,
            SUBSTATUS_INICIAL_FILA,
            [{"observacao_prodesp": f"{saida_cs} {texto_cs}"}],
        ),
        None,
    )
    contratada_prefix = f"[{SUBSTATUS_AGUARDA_CONTRATADA}]"
    texto_contratada = "c" * AGUARDA_EXTERNO_MIN_CHARS
    check_eq(
        "com suporte para aguarda contratada exige prefixo contratada",
        check_observacao_substatus_transicao(
            SUBSTATUS_COM_SUPORTE,
            SUBSTATUS_AGUARDA_CONTRATADA,
            [{"observacao_prodesp": f"{contratada_prefix} {texto_contratada}"}],
        ),
        None,
    )
    check_bool(
        "com suporte para contratada nao aceita saida com suporte",
        check_observacao_substatus_transicao(
            SUBSTATUS_COM_SUPORTE,
            SUBSTATUS_AGUARDA_CONTRATADA,
            [{"observacao_prodesp": f"{saida_cs} {texto_cs}"}],
        )
        is not None,
        True,
    )

    saida_gestao_prefix = f"[{SUBSTATUS_AGUARDA_GESTAO} - saída]"
    texto_gestao = "g" * AGUARDA_GESTAO_MIN_CHARS
    check_bool(
        "saida gestao obs curta",
        check_observacao_substatus_transicao(
            SUBSTATUS_AGUARDA_GESTAO,
            SUBSTATUS_INICIAL_FILA,
            [{"observacao_prodesp": f"{saida_gestao_prefix} curta"}],
        )
        is not None,
        True,
    )
    check_eq(
        "saida gestao obs ok",
        check_observacao_substatus_transicao(
            SUBSTATUS_AGUARDA_GESTAO,
            SUBSTATUS_INICIAL_FILA,
            [{"observacao_prodesp": f"{saida_gestao_prefix} {texto_gestao}"}],
        ),
        None,
    )

    contratada_prefix = f"[{SUBSTATUS_AGUARDA_CONTRATADA}]"
    texto_contratada = "c" * 10
    check_bool(
        "gestao para aguarda contratada sem obs",
        check_observacao_substatus_transicao(
            SUBSTATUS_AGUARDA_GESTAO,
            SUBSTATUS_AGUARDA_CONTRATADA,
            None,
        )
        is not None,
        True,
    )
    check_eq(
        "gestao para aguarda contratada com prefixo correto",
        check_observacao_substatus_transicao(
            SUBSTATUS_AGUARDA_GESTAO,
            SUBSTATUS_AGUARDA_CONTRATADA,
            [{"observacao_prodesp": f"{contratada_prefix} {texto_contratada}"}],
        ),
        None,
    )
    check_bool(
        "gestao para aguarda contratada nao exige saida gestao",
        check_observacao_substatus_transicao(
            SUBSTATUS_AGUARDA_GESTAO,
            SUBSTATUS_AGUARDA_CONTRATADA,
            [{"observacao_prodesp": f"{contratada_prefix} {texto_contratada}"}],
        )
        is None,
        True,
    )
    check_bool(
        "gestao para quebra link exige saida gestao",
        check_observacao_substatus_transicao(
            SUBSTATUS_AGUARDA_GESTAO,
            "Quebra Link",
            [{"observacao_prodesp": f"{saida_gestao_prefix} {texto_gestao}"}],
        )
        is None,
        True,
    )
    check_bool(
        "gestao para quebra link sem obs bloqueia",
        check_observacao_substatus_transicao(
            SUBSTATUS_AGUARDA_GESTAO,
            "Quebra Link",
            None,
        )
        is not None,
        True,
    )

    check_bool(
        "triagem legado conta como gestao",
        is_substatus_gestao("Triagem"),
        True,
    )
    check_bool(
        "ag gp registra analista em gestao",
        deve_registrar_analista_agendamento_gestao(
            SUBSTATUS_AGUARDA_GESTAO,
            SUBSTATUS_AGUARDA_GESTAO,
            is_agendamento_gp=True,
        ),
        True,
    )
    check_bool(
        "ag gp nao registra em retorno fila para gestao",
        deve_registrar_analista_agendamento_gestao(
            SUBSTATUS_INICIAL_FILA,
            SUBSTATUS_AGUARDA_GESTAO,
            is_agendamento_gp=True,
        ),
        False,
    )
    check_bool(
        "ag gp nao registra analista em retorno fila",
        deve_registrar_analista_agendamento_gestao(
            "Em Configuração Remota",
            SUBSTATUS_AGUARDA_GESTAO,
            is_agendamento_gp=True,
        ),
        False,
    )


def test_hostname_obrigatorio_transicao():
    """Hostname exigido ao sair de Em Configuração Remota ou concluir."""
    from prodesp.prodesp.atendimento_business_rules import check_hostname_obrigatorio_transicao

    unidade_com_host = {"hostname_unidades": "fgt-spk-test"}
    unidade_sem_host = {"hostname_unidades": ""}

    check_eq(
        "saida config remota sem hostname",
        check_hostname_obrigatorio_transicao(
            unidade_sem_host,
            "Em Configuração Remota",
            "Aguardando Config. MPLS",
            {},
            "Em Atendimento",
            "Em Atendimento",
            substatus_mudou=True,
        ),
        "O campo Hostname é obrigatório para sair de «Em Configuração Remota» e para concluir o atendimento.",
    )
    check_eq(
        "saida config remota com hostname",
        check_hostname_obrigatorio_transicao(
            unidade_com_host,
            "Em Configuração Remota",
            "Aguardando Config. MPLS",
            {},
            "Em Atendimento",
            "Em Atendimento",
            substatus_mudou=True,
        ),
        None,
    )
    check_eq(
        "concluido sem hostname",
        check_hostname_obrigatorio_transicao(
            unidade_sem_host,
            "Em Caderno de Teste",
            "Concluído",
            {},
            "Em Atendimento",
            "Concluído",
            substatus_mudou=True,
        ),
        "O campo Hostname é obrigatório para sair de «Em Configuração Remota» e para concluir o atendimento.",
    )
    check_eq(
        "transicao sem exigencia",
        check_hostname_obrigatorio_transicao(
            unidade_sem_host,
            "Aguardando Config. Remota",
            "Em Configuração Remota",
            {},
            "Em Atendimento",
            "Em Atendimento",
            substatus_mudou=True,
        ),
        None,
    )


def test_sql_cte_ultimo_substatus_agg():
    from prodesp.app import _prodesp_sql_cte_ultimo_substatus_log_agg

    sql = _prodesp_sql_cte_ultimo_substatus_log_agg()
    check_bool("cte ult_sub nome", "ult_sub_log_agg AS" in sql, True)
    check_bool("cte group by par", "GROUP BY id_atendimentos, substatus_nome" in sql, True)
    check_bool("cte union log historico", "atendimentos_status_log" in sql and "historico" in sql, True)


def test_substatus_quebra_normal():
    from prodesp.prodesp.atendimento_business_rules import is_substatus_quebra_normal

    check_bool("quebra hardware valido", is_substatus_quebra_normal("Quebra Hardware"), True)
    check_bool("aguarda gestao invalido", is_substatus_quebra_normal("Aguarda Gestão"), False)
    check_bool("vazio invalido", is_substatus_quebra_normal(""), False)
    check_bool("quebra sci e tbra", is_substatus_quebra_normal("Quebra SCI"), False)


def test_quebra_massa_vincula_observacoes_pre_agendamento():
    """Quebra em massa alinha ao create: vincula obs da unidade antes do INSERT da quebra."""
    import inspect

    from prodesp.app import api_quebra_massa, _prodesp_quebra_massa_dedupe_ids_vgr, _prodesp_quebra_massa_processar_unidade

    helper_src = inspect.getsource(_prodesp_quebra_massa_processar_unidade)
    idx_v = helper_src.find("_prodesp_vincular_observacoes_unidade_ao_atendimento")
    idx_ins = helper_src.find("INSERT INTO observacoes")
    check_bool(
        "quebra massa vincula obs pre-agendamento antes do INSERT",
        idx_v >= 0 and idx_ins >= 0 and idx_v < idx_ins,
        True,
    )
    check_bool(
        "quebra massa commit por unidade",
        "conn.commit()" in helper_src and "FOR UPDATE" in helper_src,
        True,
    )
    check_eq(
        "quebra massa dedupe ids vgr",
        _prodesp_quebra_massa_dedupe_ids_vgr(["1", " 1 ", "2", "", "2"]),
        ["1", "2"],
    )
    route_src = inspect.getsource(api_quebra_massa)
    check_bool(
        "quebra massa usa helper por unidade",
        "_prodesp_quebra_massa_processar_unidade" in route_src,
        True,
    )
    check_bool(
        "quebra massa nao usa transacao unica no lote",
        "conn.start_transaction()" not in route_src,
        True,
    )


def test_mysql_lock_wait_timeout_mensagem_amigavel():
    exc = Exception("1205 (HY000): Lock wait timeout exceeded; try restarting transaction")
    exc.errno = 1205
    msg, is_client = message_from_mysql_exception(exc)
    check_bool("lock timeout e erro de cliente", is_client, True)
    check_bool("lock timeout mensagem amigavel", "timeout" in msg.lower() or "ocupado" in msg.lower(), True)

def test_implantacao_entrada_aguarda_gestao_permitida():
    """Implantação pode enviar atendimento para fila Aguarda Gestão (retorno no fluxo)."""
    from prodesp.prodesp.atendimento_business_rules import (
        SUBSTATUS_AGUARDA_GESTAO,
        is_entrada_aguarda_gestao,
        is_retorno_de_fila,
        mensagem_edicao_apenas_gestao,
        validar_edicao_atendimento,
    )
    from datetime import date

    check_bool(
        "entrada aguarda gestao em config",
        is_entrada_aguarda_gestao("Em Configuração Remota", SUBSTATUS_AGUARDA_GESTAO),
        True,
    )
    check_bool(
        "retorno em config para gestao",
        is_retorno_de_fila("Em Configuração Remota", SUBSTATUS_AGUARDA_GESTAO),
        True,
    )

    implantacao = {
        "admin_user": 0,
        "departamento_user": "IMPLANTAÇÃO",
        "departamentos_extras": [],
        "nome_user": "Analista Impl",
    }
    row_em_config = {
        "status_atendimentos": "Em Atendimento",
        "substatus_atendimentos": "Em Configuração Remota",
        "data_atendimentos": date.today(),
        "analista_configuracao_atendimentos": "Analista Impl",
    }
    ok, msg, _ = validar_edicao_atendimento(implantacao, row_em_config, date.today())
    check_bool("implantacao edita em config", ok, True)

    row_gestao = {
        **row_em_config,
        "substatus_atendimentos": SUBSTATUS_AGUARDA_GESTAO,
        "analista_atuante_atendimentos": "Analista Impl",
    }
    ok_g, msg_g, _ = validar_edicao_atendimento(implantacao, row_gestao, date.today())
    check_bool("implantacao bloqueado em aguarda gestao", ok_g, False)
    check_eq("msg gestao exclusiva", msg_g, mensagem_edicao_apenas_gestao())


def test_marcos_atividade_gestao_unificado():
    """Marcos da Atividade: Triagem legado entra na linha única Aguarda Gestão."""
    from collections import defaultdict
    from datetime import datetime, timedelta

    import pytz

    from prodesp.app import _prodesp_build_marcos_from_log_rows, _prodesp_marco_aguarda_gestao_merged

    tz = pytz.timezone("America/Sao_Paulo")
    t0 = tz.localize(datetime(2026, 7, 3, 9, 14, 0))
    t1 = t0 + timedelta(hours=1, minutes=4, seconds=8)
    t2 = t1 + timedelta(minutes=18)

    rows_somente_triagem = [
        {"valor_novo_log": "Triagem", "alterado_em_log": t0},
        {"valor_novo_log": "Aguardando Config. Remota", "alterado_em_log": t1},
    ]
    log = defaultdict(list)
    for row in rows_somente_triagem:
        log[row["valor_novo_log"]].append(row["alterado_em_log"])

    inicio, fim, duracao = _prodesp_marco_aguarda_gestao_merged(rows_somente_triagem, log, tz)
    check_bool("gestao merged tem inicio triagem", inicio is not None, True)
    check_bool("gestao merged tem fim", fim is not None, True)
    check_eq("gestao merged duracao triagem", int(duracao or 0), int((t1 - t0).total_seconds()))

    marcos = _prodesp_build_marcos_from_log_rows(rows_somente_triagem, tz)
    nomes = [m["marco"] for m in marcos]
    check_bool("marcos sem linha triagem", "Triagem" not in nomes, True)
    check_bool("marcos tem aguarda gestao", "Aguarda Gestão" in nomes, True)
    gestao = next(m for m in marcos if m["marco"] == "Aguarda Gestão")
    check_bool("marco gestao com duracao", (gestao.get("duracao") or 0) > 0, True)

    rows_mistos = [
        {"valor_novo_log": "Triagem", "alterado_em_log": t0},
        {"valor_novo_log": "Aguarda Gestão", "alterado_em_log": t1},
        {"valor_novo_log": "Em Configuração Remota", "alterado_em_log": t2},
    ]
    marcos_mistos = _prodesp_build_marcos_from_log_rows(rows_mistos, tz)
    check_eq("marcos mistos uma linha gestao", len([m for m in marcos_mistos if m["marco"] == "Aguarda Gestão"]), 1)
    gestao_misto = next(m for m in marcos_mistos if m["marco"] == "Aguarda Gestão")
    check_eq(
        "marcos mistos soma duracao",
        int(gestao_misto.get("duracao") or 0),
        int((t1 - t0).total_seconds() + (t2 - t1).total_seconds()),
    )


def test_atendimentos_rota_mv_opcionais_template_context():
    """Tela Atendimentos deve expor MV opcionais (WiFi) + LAN SEC/TER/QUA no contexto compartilhado."""
    import inspect

    from prodesp.app import _prodesp_atendimentos_modais_template_context, atendimentos
    from prodesp.prodesp.db_field_limits import (
        UNIDADES_LAN_EXTRA_SPEC,
        UNIDADES_MV_OPCIONAIS_SPEC,
        lan_extra_template_fields,
        mv_opcionais_template_fields,
    )

    src = inspect.getsource(atendimentos)
    check_bool(
        "atendimentos usa contexto modais compartilhado",
        "_prodesp_atendimentos_modais_template_context" in src,
        True,
    )
    ctx_src = inspect.getsource(_prodesp_atendimentos_modais_template_context)
    check_bool("contexto tem mv_opcionais_fields", "prodesp_mv_opcionais_fields" in ctx_src, True)
    check_bool("contexto tem lan_extra_fields", "prodesp_lan_extra_fields" in ctx_src, True)

    mv_fields = mv_opcionais_template_fields()
    mv_keys = {f["js_key"] for f in mv_fields}
    wifi_keys = {
        "mv_rede_wifi_guest",
        "mv_ip_wifi_guest",
        "mv_dhcp_start_wifi_guest",
        "mv_dhcp_end_wifi_guest",
        "mv_reserva_start_wifi_guest",
        "mv_reserva_end_wifi_guest",
    }
    check_eq("mv template count", len(mv_fields), len(UNIDADES_MV_OPCIONAIS_SPEC))
    for js in wifi_keys:
        check_bool(f"mv template wifi {js}", js in mv_keys, True)

    lan_fields = lan_extra_template_fields()
    lan_keys = {f["js_key"] for f in lan_fields}
    check_eq("lan extra template count", len(lan_fields), len(UNIDADES_LAN_EXTRA_SPEC))
    for js, *_ in UNIDADES_LAN_EXTRA_SPEC:
        check_bool(f"lan extra template {js}", js in lan_keys, True)

    tpl_at = (_PRODESP_ROOT / "templates" / "atendimentos_prodesp.html").read_text(encoding="utf-8")
    tpl_dash = (_PRODESP_ROOT / "templates" / "dashboard_atendimentos_prodesp.html").read_text(
        encoding="utf-8"
    )
    tpl_bp = (_PRODESP_ROOT / "templates" / "prodesp_criar_blueprint.html").read_text(encoding="utf-8")
    for name, tpl in (
        ("atendimentos", tpl_at),
        ("dashboard", tpl_dash),
        ("blueprint", tpl_bp),
    ):
        check_bool(
            f"{name} inclui partial lan extra",
            "prodesp_lan_extra_unidades.html" in tpl,
            True,
        )


def test_blueprint_download_automatico():
    """Após gerar blueprint, download automático (mesmo padrão do caderno)."""
    bp_js = (_PRODESP_ROOT / "static" / "js" / "prodesp_blueprint_confirm.js").read_text(
        encoding="utf-8"
    )
    check_bool("blueprint triggerDownload helper", "function triggerBlueprintDownload" in bp_js, True)
    check_bool("blueprint exporta triggerDownload", "triggerDownload: triggerBlueprintDownload" in bp_js, True)
    check_bool(
        "blueprint nao usa location.href no confirm",
        "global.location.href = j2.download_url" not in bp_js
        and "global.location.href = j1.download_url" not in bp_js,
        True,
    )
    check_bool("blueprint usa trigger no confirm", "triggerBlueprintDownload(j2.download_url)" in bp_js, True)

    fila = (_PRODESP_ROOT / "static" / "js" / "script_atendimentos_prodesp.js").read_text(
        encoding="utf-8"
    )
    check_bool(
        "fila blueprint triggerDownload",
        "ProdespBlueprintConfirm.triggerDownload" in fila
        or "triggerDownload(result.download_url)" in fila,
        True,
    )

    tpl_bp = (_PRODESP_ROOT / "templates" / "prodesp_criar_blueprint.html").read_text(encoding="utf-8")
    check_bool("criar blueprint data-download-url", "data-download-url" in tpl_bp, True)
    check_bool(
        "criar blueprint auto download no load",
        "triggerDownload(dlUrl)" in tpl_bp or "ProdespBlueprintConfirm.triggerDownload" in tpl_bp,
        True,
    )
    for name, path in (
        ("atendimentos", "templates/atendimentos_prodesp.html"),
        ("dashboard", "templates/dashboard_atendimentos_prodesp.html"),
        ("criar_blueprint", "templates/prodesp_criar_blueprint.html"),
    ):
        tpl = (_PRODESP_ROOT / path).read_text(encoding="utf-8")
        check_bool(f"{name} cache-bust bp-confirm-10", "bp-confirm-10" in tpl, True)


def test_blueprint_live_required_fields():
    """Hostname/acrônimo/CIDR/velocidade/LP pintados na página (não só no modal)."""
    live = (_PRODESP_ROOT / "static" / "js" / "prodesp_live_field_validation.js").read_text(
        encoding="utf-8"
    )
    check_bool("live validateBlueprintForm", "function validateBlueprintForm" in live, True)
    check_bool("live paint hostname/acronimo", "function paintRequiredTextField" in live, True)
    check_bool("live paint CIDR", "function paintCidrIpField" in live, True)
    check_bool("live paint velocidade required", "function paintVelocityRequiredField" in live, True)
    # Regressão: sucesso deve retornar valid:true (não só o meta do paintVelocityMbpsField).
    check_bool(
        "live paintVelocityRequiredField retorna valid true no path ok",
        "valid: true" in live
        and "paintVelocityMbpsField(el, !!(opts && opts.afterNormalize))" in live
        and "return paintVelocityMbpsField(el" not in live,
        True,
    )
    check_bool(
        "live clear presence apos preencher designador/id_vgr",
        "function clearBlueprintLinkPresenceField" in live
        and "function paintBlueprintLinkIdentifierOk" in live
        and "data-prodesp-presence" in live,
        True,
    )
    check_bool("live designador LP hint", "Designador (LP)" in live, True)
    check_bool(
        "live paint server pendencias",
        "function paintBlueprintServerPendencias" in live,
        True,
    )
    check_bool("live bind required fields", "function bindBlueprintRequiredLiveFields" in live, True)
    check_bool("live exige ao menos 1 link", "Pelo menos um link (MPLS ou STATIC)" in live, True)
    check_bool("live serial no validate", "Serial Number do Equipamento" in live, True)
    check_bool("live WAN obrigatorio", "IP WAN é obrigatório" in live, True)
    check_bool("live Gateway obrigatorio", "IP Gateway é obrigatório" in live, True)
    check_bool("live paintCoordinateField", "function paintCoordinateField" in live, True)

    bp_js = (_PRODESP_ROOT / "static" / "js" / "prodesp_blueprint_confirm.js").read_text(
        encoding="utf-8"
    )
    check_bool(
        "confirm pinta pendencias na pagina",
        "paintBlueprintServerPendencias" in bp_js,
        True,
    )

    tpl_bp = (_PRODESP_ROOT / "templates" / "prodesp_criar_blueprint.html").read_text(encoding="utf-8")
    check_bool("criar blueprint novalidate", "novalidate" in tpl_bp, True)
    check_bool("criar blueprint cache bp-req-6", "bp-req-6" in tpl_bp, True)
    check_bool(
        "criar blueprint valida antes do modal",
        "validateBlueprintForm" in tpl_bp,
        True,
    )
    check_bool(
        "live paint no load",
        "function paintBlueprintInitialState" in live and "paintBlueprintInitialState(form)" in live,
        True,
    )


def test_dt_sync_dismiss_overlays():
    """Sync fecha overlays e só recarrega a tabela se data_revision mudou."""
    sync = (_PRODESP_ROOT / "static" / "js" / "prodesp_dt_sync.js").read_text(encoding="utf-8")
    check_bool("dt_sync dismissTransientOverlays", "dismissTransientOverlays" in sync, True)
    check_bool("dt_sync fecha dtcc-dropdown", "div.dtcc-dropdown" in sync, True)
    check_bool("dt_sync skip modal aberto", "hasOpenModal" in sync and "modal.show" in sync, True)
    check_bool("dt_sync limpa backdrop orfao", "cleanupModalArtifacts" in sync or "modal-backdrop" in sync, True)
    check_bool("dt_sync skip reload se revisao igual", "shouldReload" in sync and "Number(rev)" in sync, True)
    check_bool("dt_sync checkNow leve", "function checkNow" in sync or "checkNow()" in sync, True)
    check_bool("dt_sync passa sinceRevision ao onReload", "onReload(!!force, sinceRevision)" in sync, True)
    fila = (_PRODESP_ROOT / "static" / "js" / "script_atendimentos_prodesp.js").read_text(encoding="utf-8")
    check_bool("fila visibility usa checkNow", "prodespFilaDtSync.checkNow" in fila, True)
    check_bool("fila processing true", "processing: true" in fila, True)
    check_bool("fila sync delta helper", "prodespFilaSyncReload" in fila, True)
    check_bool("fila delta fallback full", "fallback_full" in fila, True)
    check_bool("fila delta fase2 add row", "table.row.add" in fila and "removed_ids" in fila, True)
    check_bool("fila delta fase2 KPIs", "updateTopCards(payload.resumo)" in fila, True)
    check_bool(
        "fila delta fase2 ColumnControl",
        "prodespRefreshColumnOptionsFromDeltaRows" in fila,
        True,
    )
    check_bool("fila delta nao fallback so por removed", "payload.removed_ids && payload.removed_ids.length" not in fila, True)
    tpl = (_PRODESP_ROOT / "templates" / "atendimentos_prodesp.html").read_text(encoding="utf-8")
    check_bool("fila template PRODESP_LIST_DELTA", "PRODESP_LIST_DELTA" in tpl, True)
    query = (_PRODESP_ROOT / "prodesp" / "atendimentos_list_query.py").read_text(encoding="utf-8")
    check_bool("list_delta_enabled flag", "list_delta_enabled" in query and "PRODESP_ATENDIMENTOS_LIST_DELTA" in query, True)
    check_bool("build_rows_by_ids_query", "build_rows_by_ids_query" in query, True)
    app_py = (_PRODESP_ROOT / "app.py").read_text(encoding="utf-8")
    check_bool("rota atendimentos_list_delta", "atendimentos_list_delta" in app_py, True)
    check_bool("delta inclui resumo KPI", '"resumo": resumo' in app_py or "resumo" in app_py, True)
    check_bool(
        "delta fase2 sem fallback por removed",
        "fallback_full = bool(removed_ids)" not in app_py,
        True,
    )
    check_bool("bust passa ids ao bump", "bump(atendimento_ids=clean)" in app_py, True)


def test_dashboard_refresh_unificado():
    """Dashboard gestão: KPIs e tabela no mesmo ciclo, sync ao minuto, reload ao focar aba."""
    js = _PRODESP_ROOT / "static" / "js" / "script_gestao_atendimentos_prodesp.js"
    src = js.read_text(encoding="utf-8")
    check_bool("dashboard usa ProdespDtSync", "prodespGestaoDtSync" in src and "ProdespDtSync.create" in src, True)
    check_bool(
        "dashboard visibility checkNow",
        "visibilitychange" in src and "prodespGestaoDtSync.checkNow" in src,
        True,
    )
    dash_tpl = _PRODESP_ROOT / "templates" / "dashboard_atendimentos_prodesp.html"
    check_bool("dashboard botao atualizar", "btnProdespDtRefreshNow" in dash_tpl.read_text(encoding="utf-8"), True)
    check_bool("dashboard sem poll kpis separado", "refreshDashboardKpisOnly" not in src, True)
    check_bool("dashboard refresh unificado", "prodespAfterDashboardDataLoaded" in src, True)
    check_bool("dashboard refresh imediato ao mudar data", "prodespRefreshDashboardForCurrentDates" in src, True)
    check_bool("dashboard periodo aplicado separado", "dashboardDatesAtLastApply" in src, True)
    check_bool("dashboard abort ajax defasado", "latestDashboardLoadSeq" in src and "dashboardAjaxXhr.abort" in src, True)
    check_bool("dashboard normaliza intervalo datas", "prodespNormalizeDashboardDateRange" in src, True)
    check_bool("dashboard sem lock dia unico", "wasSingleDay" not in src, True)
    check_bool(
        "dashboard normaliza pelo campo alterado",
        'changedId === "startDate"' in src and 'changedId === "endDate"' in src,
        True,
    )
    check_bool("dashboard allowFuture periodo", "prodespAllowFutureDashboardDates" in src, True)
    check_bool("dashboard presets periodo", "prodespAplicarPresetPeriodoDashboard" in src, True)
    check_bool("dashboard zera kpis ao trocar periodo", "prodespMarkDashboardPeriodPending" in src, True)
    check_bool("dashboard valida datas da resposta", "prodespDashboardLoadAccepted" in src, True)
    check_bool("dashboard meta por seq dataSrc", "dashboardLoadMetaBySeq" in src, True)
    check_bool("dashboard reload complete recovery", "prodespOnDashboardReloadComplete" in src, True)
    dash_html = dash_tpl.read_text(encoding="utf-8")
    check_bool("dashboard carrega login_periodo_datas", "login_periodo_datas.js" in dash_html, True)
    check_bool("dashboard botao preset hoje", 'data-prodesp-periodo-preset="hoje"' in dash_html, True)
    check_bool("dashboard botao preset ontem", 'data-prodesp-periodo-preset="ontem"' in dash_html, True)
    check_bool("dashboard botao preset 7d", 'data-prodesp-periodo-preset="7d"' in dash_html, True)
    check_bool(
        "dashboard sem hint periodo longo",
        "Altere início e fim independentemente" not in dash_html,
        True,
    )

    js_at = _PRODESP_ROOT / "static" / "js" / "script_atendimentos_prodesp.js"
    src_at = js_at.read_text(encoding="utf-8")
    check_bool(
        "perm save entrada aguarda gestao",
        "prodespResolvePermEdicaoModalSalvar" in src_at
        and "prodespIsEntradaAguardaGestao" in src_at,
        True,
    )
    flow_js = _PRODESP_ROOT / "static" / "js" / "prodesp_substatus_flow.js"
    flow_src = flow_js.read_text(encoding="utf-8")
    check_bool(
        "export entrada aguarda gestao",
        "global.prodespIsEntradaAguardaGestao" in flow_src,
        True,
    )
    check_bool(
        "export entrada aguarda externo",
        "global.prodespIsEntradaAguardaExterno" in flow_src,
        True,
    )
    check_bool(
        "export saida pre quebra",
        "global.prodespRunObservacaoSaidaPreQuebra" in flow_src,
        True,
    )
    check_bool(
        "edit substatus listener unico",
        src_at.count("substatusSelect._quebraChangeListener = async") == 0,
        True,
    )


def test_colunas_analista_liberar_retorno_fila():
    """Zera analista da etapa ao voltar para fila Aguardando (regra do modal)."""
    from prodesp.prodesp.atendimento_business_rules import (
        colunas_analista_liberar_substatus_transicao,
    )

    clears = colunas_analista_liberar_substatus_transicao(
        "Em Configuração Remota",
        "Aguardando Config. Remota",
    )
    check_eq(
        "retorno em config para fila config",
        clears.get("analista_configuracao_atendimentos"),
        "",
    )
    check_bool(
        "retorno em config para fila config nao zera gestao",
        "analista_atuante_atendimentos" not in clears,
        True,
    )

    clears_gestao = colunas_analista_liberar_substatus_transicao(
        "Em Configuração Remota",
        SUBSTATUS_AGUARDA_GESTAO,
    )
    check_eq(
        "retorno em config para gestao zera config",
        clears_gestao.get("analista_configuracao_atendimentos"),
        "",
    )
    check_eq(
        "retorno em config para gestao zera gestao",
        clears_gestao.get("analista_atuante_atendimentos"),
        "",
    )


def test_relatorio_analitico_metricas_etapa():
    """Início e tempo por etapa no relatório analítico (log de substatus)."""
    from datetime import datetime

    import pandas as pd
    import pytz

    from datetime import date as date_cls

    from prodesp.app import (
        _PRODESP_ETAPAS_RELATORIO_ANALITICO,
        _prodesp_format_data_agendamento_relatorio,
        _prodesp_inicio_primeira_etapa_log,
        _prodesp_metricas_etapas_relatorio,
        _prodesp_reordenar_colunas_relatorio_atendimentos,
        duracao_acumulada_substatus_segundos,
        format_hora_agendamento_input,
    )

    tz = pytz.timezone("America/Sao_Paulo")
    t0 = tz.localize(datetime(2025, 6, 1, 10, 0, 0))
    t1 = tz.localize(datetime(2025, 6, 1, 10, 30, 0))
    logs = [
        {"valor_novo_log": "Aguardando Config. Remota", "alterado_em_log": t0},
        {"valor_novo_log": "Em Configuração Remota", "alterado_em_log": t1},
    ]
    inicio = _prodesp_inicio_primeira_etapa_log(
        logs, ("Aguardando Config. Remota",), tz
    )
    check_eq("inicio etapa ag config remota so hora", inicio, "10:00:00")

    df_logs = pd.DataFrame(
        [
            {
                "id_atendimentos_log": 99,
                "valor_novo_log": "Aguarda Gestão",
                "alterado_em_log": t0,
            },
            {
                "id_atendimentos_log": 99,
                "valor_novo_log": SUBSTATUS_INICIAL_FILA,
                "alterado_em_log": t1,
            },
        ]
    )
    df_m = _prodesp_metricas_etapas_relatorio(df_logs, tz)
    check_eq("metricas linhas", len(df_m), 1)
    check_eq("metricas id", int(df_m.iloc[0]["id_atendimentos"]), 99)
    check_eq(
        "metricas inicio gestao so hora",
        df_m.iloc[0]["Início Aguarda Gestão"],
        "10:00:00",
    )
    check_bool(
        "relatorio etapas inclui com suporte",
        any(lbl == SUBSTATUS_COM_SUPORTE for lbl, _ in _PRODESP_ETAPAS_RELATORIO_ANALITICO),
        True,
    )

    from prodesp.prodesp.gestao.relatorio_tempos import COL_TEMPO_ATENDIMENTO

    df_ord = _prodesp_reordenar_colunas_relatorio_atendimentos(
        pd.DataFrame(
            columns=[
                "Hostname",
                "Analista Gestão",
                "Analista Caderno de Teste",
                "Início Aguarda Gestão",
                "Tempo Aguarda Gestão",
                COL_TEMPO_ATENDIMENTO,
                "Links",
                "ID VGR",
                "Data Agendamento",
                "Hora Agendamento",
                "Data Atendimento",
            ]
        )
    )
    check_eq("ordem analista gestao", df_ord.columns[0], "ID VGR")
    cols = list(df_ord.columns)
    check_eq("ordem data agendamento", cols[1], "Data Agendamento")
    check_eq("ordem hora agendamento", cols[2], "Hora Agendamento")
    check_eq("ordem data atendimento", cols[3], "Data Atendimento")
    check_eq(
        "format data agendamento relatorio",
        _prodesp_format_data_agendamento_relatorio(date_cls(2026, 6, 10)),
        "10/06/2026",
    )
    check_eq(
        "format hora agendamento relatorio",
        format_hora_agendamento_input("14:30:00"),
        "14:30",
    )

    from unittest.mock import MagicMock

    from prodesp.app import (
        _prodesp_enriquecer_agendamento_historico_asof,
        _prodesp_relatorio_aplicar_agenda_datatable,
        _prodesp_sem_id_atendimento,
        _prodesp_valor_sql_nulo,
    )

    check_bool("sem id atendimento None", _prodesp_sem_id_atendimento(None), True)
    check_bool("sem id atendimento NaN", _prodesp_sem_id_atendimento(float("nan")), True)
    check_bool("sem id atendimento valido", _prodesp_sem_id_atendimento(42), False)

    cursor_mock = MagicMock()
    df_agenda = pd.DataFrame(
        [
            {
                "id_atendimentos": float("nan"),
                "id_unidades": 100,
                "_data_agendamento_raw": date_cls(2026, 6, 18),
                "_hora_agendamento_raw": "09:30:00",
                "_data_atendimento_raw": float("nan"),
                "Status": "Agendado",
            }
        ]
    )
    out_ag = _prodesp_relatorio_aplicar_agenda_datatable(cursor_mock, df_agenda, "2026-06-18")
    check_eq("relatorio agendado data", out_ag.iloc[0]["Data Agendamento"], "18/06/2026")
    check_eq("relatorio agendado hora", out_ag.iloc[0]["Hora Agendamento"], "09:30")

    import pandas as pd
    from datetime import timedelta

    df_td = pd.DataFrame(
        [
            {
                "id_atendimentos": float("nan"),
                "id_unidades": 102,
                "_data_agendamento_raw": date_cls(2026, 6, 22),
                "_hora_agendamento_raw": pd.Timedelta(hours=15),
                "_data_atendimento_raw": float("nan"),
                "Status": "Agendado",
            }
        ]
    )
    out_td = _prodesp_relatorio_aplicar_agenda_datatable(cursor_mock, df_td, "2026-06-22")
    check_eq(
        "relatorio agendado hora pd.Timedelta",
        out_td.iloc[0]["Hora Agendamento"],
        "15:00",
    )

    df_pytd = pd.DataFrame(
        [
            {
                "id_atendimentos": None,
                "id_unidades": 103,
                "_data_agendamento_raw": date_cls(2026, 6, 22),
                "_hora_agendamento_raw": timedelta(hours=14, minutes=30),
                "_data_atendimento_raw": None,
                "Status": "Agendado",
            }
        ]
    )
    out_pytd = _prodesp_relatorio_aplicar_agenda_datatable(cursor_mock, df_pytd, "2026-06-22")
    check_eq(
        "relatorio agendado hora timedelta",
        out_pytd.iloc[0]["Hora Agendamento"],
        "14:30",
    )

    rows_enrich = [
        {
            "id_atendimentos": float("nan"),
            "id_unidades": 101,
            "data_agendamento": date_cls(2026, 6, 20),
            "hora_agendamento": "14:00:00",
        }
    ]
    _prodesp_enriquecer_agendamento_historico_asof(cursor_mock, rows_enrich, date_cls(2026, 6, 20))
    check_eq(
        "enrich agendado NaN id data",
        rows_enrich[0]["data_agendamento"],
        date_cls(2026, 6, 20),
    )
    check_eq("enrich agendado NaN id hora", rows_enrich[0]["hora_agendamento"], "14:00:00")

    check_bool(
        "caderno apos mpls",
        cols.index("Analista Caderno de Teste") > cols.index("Analista Gestão"),
        True,
    )
    check_bool(
        "tempos no final do relatorio",
        cols.index(COL_TEMPO_ATENDIMENTO) > cols.index("Links"),
        True,
    )
    # Ordem atual: totais (VITA/Atendimento) depois Links; início/tempo por etapa em seguida.
    check_bool(
        "tempo total antes inicio gestao",
        cols.index(COL_TEMPO_ATENDIMENTO) < cols.index("Início Aguarda Gestão"),
        True,
    )
    check_bool(
        "inicio gestao apos links",
        cols.index("Início Aguarda Gestão") > cols.index("Links"),
        True,
    )

    from datetime import timedelta

    t2 = t1 + timedelta(minutes=30)
    t3 = t1 + timedelta(hours=1)
    logs_duas_gestoes = [
        {"valor_novo_log": "Aguarda Gestão", "alterado_em_log": t0},
        {"valor_novo_log": "Aguardando Config. Remota", "alterado_em_log": t1},
        {"valor_novo_log": "Aguarda Gestão", "alterado_em_log": t2},
        {"valor_novo_log": "Em Configuração Remota", "alterado_em_log": t3},
    ]
    seg_gestao = duracao_acumulada_substatus_segundos(
        logs_duas_gestoes, "Aguarda Gestão", tz
    )
    check_bool("tempo gestao soma multiplas passagens", seg_gestao == 60 * 60, True)

    from prodesp.app import inicio_ultima_entrada_substatus

    t_cfg1 = tz.localize(datetime(2025, 6, 1, 11, 10, 0))
    t_gestao = tz.localize(datetime(2025, 6, 1, 11, 30, 0))
    t_cfg2 = tz.localize(datetime(2025, 6, 1, 15, 30, 0))
    logs_config_remota = [
        {"valor_novo_log": "Em Configuração Remota", "alterado_em_log": t_cfg1},
        {"valor_novo_log": "Aguarda Gestão", "alterado_em_log": t_gestao},
        {"valor_novo_log": "Em Configuração Remota", "alterado_em_log": t_cfg2},
    ]
    ult_cfg = inicio_ultima_entrada_substatus(logs_config_remota, "Em Configuração Remota")
    check_eq("ultima entrada config remota", ult_cfg, t_cfg2)

    # ID VGR 2177965: status_log incompleto (trigger antiga); historico tem reentrada 13:44:47
    t_cfg_antiga = tz.localize(datetime(2026, 6, 18, 9, 49, 49))
    t_aguarda = tz.localize(datetime(2026, 6, 18, 10, 47, 50))
    t_aguard_cfg = tz.localize(datetime(2026, 6, 18, 13, 11, 41))
    t_cfg_reentrada = tz.localize(datetime(2026, 6, 18, 13, 44, 47))
    logs_incompletos_1225 = [
        {"valor_novo_log": "Aguardando Config. Remota", "alterado_em_log": tz.localize(datetime(2026, 6, 18, 9, 41, 51))},
        {"valor_novo_log": "Em Configuração Remota", "alterado_em_log": t_cfg_antiga},
        {"valor_novo_log": "Aguarda Gestão", "alterado_em_log": t_aguarda},
    ]
    logs_com_historico = logs_incompletos_1225 + [
        {"valor_novo_log": "Aguardando Config. Remota", "alterado_em_log": t_aguard_cfg},
        {"valor_novo_log": "Em Configuração Remota", "alterado_em_log": t_cfg_reentrada},
    ]
    check_eq(
        "status_log incompleto usa primeira entrada config",
        inicio_ultima_entrada_substatus(logs_incompletos_1225, "Em Configuração Remota"),
        t_cfg_antiga,
    )
    check_eq(
        "timeline completa usa reentrada config remota",
        inicio_ultima_entrada_substatus(logs_com_historico, "Em Configuração Remota"),
        t_cfg_reentrada,
    )

    from prodesp.prodesp.gestao.relatorio_tempos import _log_evento_ja_coberto

    check_bool(
        "historico duplicado nao re-insere",
        _log_evento_ja_coberto(logs_incompletos_1225, "Em Configuração Remota", t_cfg_antiga),
        True,
    )
    check_bool(
        "historico novo evento detectado",
        _log_evento_ja_coberto(logs_incompletos_1225, "Em Configuração Remota", t_cfg_reentrada),
        False,
    )


def test_janela_envio_relatorio_gestao():
    from datetime import datetime
    import os

    import pytz

    from prodesp.prodesp.gestao.gestao_relatorio_scheduler import (
        dia_util,
        dentro_janela_envio,
        slot_relatorio_gestao,
    )

    # Isola do .env local (ex.: HORA_FIM=23) — regra padrão documental: 10h–18h (:00).
    prev_ini = os.environ.get("PRODESP_GESTAO_RELATORIO_HORA_INICIO")
    prev_fim = os.environ.get("PRODESP_GESTAO_RELATORIO_HORA_FIM")
    os.environ["PRODESP_GESTAO_RELATORIO_HORA_INICIO"] = "10"
    os.environ["PRODESP_GESTAO_RELATORIO_HORA_FIM"] = "18"
    try:
        tz = pytz.timezone("America/Sao_Paulo")
        check_bool(
            "dia util segunda",
            dia_util(tz.localize(datetime(2026, 6, 8, 10, 0, 0))),
            True,
        )
        check_bool(
            "dia util sabado",
            dia_util(tz.localize(datetime(2026, 6, 13, 10, 0, 0))),
            False,
        )
        check_bool(
            "dia util domingo",
            dia_util(tz.localize(datetime(2026, 6, 14, 10, 0, 0))),
            False,
        )
        check_bool(
            "janela 10h00",
            dentro_janela_envio(tz.localize(datetime(2026, 6, 10, 10, 0, 0))),
            True,
        )
        check_bool(
            "janela 10h15",
            dentro_janela_envio(tz.localize(datetime(2026, 6, 10, 10, 15, 0))),
            True,
        )
        check_bool(
            "janela 17h30",
            dentro_janela_envio(tz.localize(datetime(2026, 6, 10, 17, 30, 0))),
            True,
        )
        check_bool(
            "fora 09h30",
            dentro_janela_envio(tz.localize(datetime(2026, 6, 10, 9, 30, 0))),
            False,
        )
        check_bool(
            "fora 18h30",
            dentro_janela_envio(tz.localize(datetime(2026, 6, 10, 18, 30, 0))),
            False,
        )
        check_eq(
            "slot 10h15",
            slot_relatorio_gestao(tz.localize(datetime(2026, 6, 10, 10, 15, 0))),
            "2026-06-10 10:00",
        )
        check_eq(
            "slot 10h45",
            slot_relatorio_gestao(tz.localize(datetime(2026, 6, 10, 10, 45, 0))),
            "2026-06-10 10:30",
        )
    finally:
        if prev_ini is None:
            os.environ.pop("PRODESP_GESTAO_RELATORIO_HORA_INICIO", None)
        else:
            os.environ["PRODESP_GESTAO_RELATORIO_HORA_INICIO"] = prev_ini
        if prev_fim is None:
            os.environ.pop("PRODESP_GESTAO_RELATORIO_HORA_FIM", None)
        else:
            os.environ["PRODESP_GESTAO_RELATORIO_HORA_FIM"] = prev_fim


def test_relatorio_obs_format_cell():
    from prodesp.app import _prodesp_format_relatorio_observacoes_cell

    raw = "2026-06-11 10:30:00: Devido a ferramenta"
    out = _prodesp_format_relatorio_observacoes_cell(raw)
    check_eq("fmt obs data br", out, "11/06/2026 10:30: Devido a ferramenta")


def test_kpis_relatorio_gestao_email():
    """KPIs do relatório executivo alinhados ao dashboard."""
    from prodesp.prodesp.gestao.gestao_relatorio_email import calcular_kpis_gestao, kpis_por_contratada

    rows = [
        {"id_atendimento": None, "status_atendimentos": "Agendado", "contratada_atendimentos": "DELFIA"},
        {
            "id_atendimento": 1,
            "status_atendimentos": "Em Atendimento",
            "substatus_atendimentos": "Aguardando Cliente",
            "contratada_atendimentos": "DELFIA",
            "tempo_em_segundos": 3600,
        },
        {
            "id_atendimento": 10,
            "status_atendimentos": "Em Atendimento",
            "substatus_atendimentos": "Aguarda Gestão",
            "contratada_atendimentos": "DELFIA",
        },
        {
            "id_atendimento": 11,
            "status_atendimentos": "Em Atendimento",
            "substatus_atendimentos": "Aguarda Contratada",
            "contratada_atendimentos": "DELFIA",
        },
        {
            "id_atendimento": 12,
            "status_atendimentos": "Em Atendimento",
            "substatus_atendimentos": "Aguarda Licença",
            "contratada_atendimentos": "SPREAD",
        },
        {
            "id_atendimento": 2,
            "status_atendimentos": "Concluído",
            "substatus_atendimentos": "Concluído",
            "contratada_atendimentos": "INELCOM",
            "tempo_em_segundos": 7200,
        },
        {
            "id_atendimento": 3,
            "status_atendimentos": "Quebra",
            "substatus_atendimentos": "Quebra",
            "contratada_atendimentos": "INELCOM",
        },
        {
            "id_atendimento": 4,
            "status_atendimentos": "Quebra TBRA",
            "substatus_atendimentos": "Quebra SCI",
            "contratada_atendimentos": "INELCOM",
        },
    ]
    kpi = calcular_kpis_gestao(rows)
    check_eq("kpi email total", kpi.total, 8)
    check_eq("kpi email agendados", kpi.agendados, 1)
    check_eq("kpi email com atividade", kpi.com_atividade, 7)
    check_eq("kpi email em atendimento", kpi.em_atendimento, 4)
    check_eq("kpi email aguardando cliente", kpi.aguardando_cliente, 1)
    check_eq("kpi email aguarda gestao", kpi.aguarda_gestao, 1)
    check_eq("kpi email aguarda contratada", kpi.aguarda_contratada, 1)
    check_eq("kpi email aguarda licenca", kpi.aguarda_licenca, 1)
    check_eq("kpi email migrados", kpi.migrados, 1)
    check_eq("kpi email quebra", kpi.quebra, 1)
    check_eq("kpi email quebra tbra", kpi.quebra_tbra, 1)
    check_eq("kpi email pct migrados", kpi.pct_migrados, 12)

    from prodesp.prodesp.gestao.gestao_relatorio_email import (
        calc_pct_migrados_gestao,
        contratada_row_key,
    )

    check_eq("pct migrados formula 1/8", calc_pct_migrados_gestao(1, 8), 12)
    check_eq("pct migrados formula zero total", calc_pct_migrados_gestao(5, 0), 0)
    check_eq(
        "contratada agendado planejada",
        contratada_row_key(
            {"contratada_planejada_unidades": "DELFIA", "contratada_atendimentos": ""}
        ),
        "DELFIA",
    )
    check_eq(
        "contratada ativo fallback planejada",
        contratada_row_key(
            {
                "id_atendimento": 1,
                "contratada_atendimentos": "",
                "contratada_planejada_unidades": "INELCOM",
            }
        ),
        "INELCOM",
    )
    check_eq("kpi email tempo medio", kpi.tempo_medio, "01:30:00")

    from prodesp.prodesp.gestao.gestao_relatorio_email import (
        RELATORIO_COLUNAS,
        linhas_relatorio_executivo,
    )

    linha = linhas_relatorio_executivo(
        [
            {
                "id_atendimento": 9,
                "id_vgr": "123",
                "data_agendamento": "2026-06-15",
                "hora_agendamento": "10:00:00",
                "data_atendimentos": "2026-06-15",
                "status_atendimentos": "Em Atendimento",
                "substatus_atendimentos": "Aguarda Gestão",
                "contratada_atendimentos": "DELFIA",
                "horario_inicio": "10:15:00",
                "endereco": "Rua A",
                "municipio": "São Paulo",
                "estado": "SP",
                "acronimo": "LOJA",
                "nome": "Centro",
                "ticket_noc": "INC123456",
            }
        ],
        {},
        {},
    )[0]
    check_eq("relatorio col substatus", linha["Substatus"], "Aguarda Gestão")
    check_eq("relatorio col hora agendamento", linha["Hora Agendamento"], "10:00")
    check_eq("relatorio col tck noc", linha["Tck NOC"], "INC123456")
    check_eq("relatorio col inicio", linha["Início da Atividade"], "10:15")
    check_eq("relatorio col cidade", linha["Cidade"], "São Paulo")
    check_eq("relatorio col uf", linha["UF"], "SP")
    check_bool(
        "relatorio col ordem substatus",
        RELATORIO_COLUNAS.index("Substatus") == RELATORIO_COLUNAS.index("Status") + 1,
        True,
    )
    check_bool(
        "relatorio col ordem motivo",
        RELATORIO_COLUNAS.index("Motivo") == RELATORIO_COLUNAS.index("Substatus") + 1,
        True,
    )
    check_bool(
        "relatorio col ordem inicio",
        RELATORIO_COLUNAS.index("Início da Atividade") == RELATORIO_COLUNAS.index("Contratada") + 1,
        True,
    )
    check_bool(
        "relatorio col ordem horario fim",
        RELATORIO_COLUNAS.index("Horário Finalização")
        == RELATORIO_COLUNAS.index("Início da Atividade") + 1,
        True,
    )
    check_bool(
        "relatorio col ordem tck noc",
        RELATORIO_COLUNAS.index("Tck NOC") == RELATORIO_COLUNAS.index("Observações") + 1,
        True,
    )

    from prodesp.prodesp.gestao.gestao_relatorio_email import (
        _KPI_CARD_HEIGHT,
        _MODERN_CARD_WIDTH,
        _MSO_BORDER,
        _kpi_grid_dual_html,
        _kpi_grid_modern_html,
        _kpi_grid_table_html,
    )

    html_kpi = _kpi_grid_dual_html(calcular_kpis_gestao(rows))
    check_bool("email kpi dual mso", "<!--[if mso]>" in html_kpi, True)
    check_bool("email kpi dual modern", "<!--[if !mso]><!-->" in html_kpi, True)
    check_bool("email kpi classic usa tabela", "<table role='presentation'" in html_kpi, True)
    check_bool(
        "email kpi classic altura fixa",
        f"height='{_KPI_CARD_HEIGHT}'" in html_kpi,
        True,
    )
    html_modern = _kpi_grid_modern_html(calcular_kpis_gestao(rows))
    check_bool("email kpi modern inline-block", "display:inline-block" in html_modern, True)
    check_bool(
        "email kpi modern largura uniforme",
        f"width:{_MODERN_CARD_WIDTH}" in html_modern,
        True,
    )
    check_bool("email kpi modern altura natural", "height:68" not in html_modern, True)
    check_bool("email kpi modern sem altura fixa attr", "height='" not in html_modern, True)
    check_bool("email kpi modern sem card largo", "width:200px" not in html_modern, True)
    html_classic = _kpi_grid_table_html(calcular_kpis_gestao(rows))
    check_bool("email kpi classic sem inline-block", "inline-block" not in html_classic, True)
    check_bool("email kpi classic barra sem borda esquerda", _MSO_BORDER in html_classic, True)
    check_bool("email kpi hint reservado classic", "&nbsp;" in html_classic, True)
    por_c = kpis_por_contratada(rows)
    check_eq("kpi por contratada delafia total", por_c["DELFIA"].total, 4)
    check_eq("kpi por contratada inelcom migrados", por_c["INELCOM"].migrados, 1)


def test_leitura_concluido_perfil_gestao():
    """AG/GP/Supervisor podem abrir detalhes de concluídos no dashboard de gestão."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from run import app
    from prodesp.app import _prodesp_resposta_leitura_concluido

    ag_gp = SimpleNamespace(
        admin_user=0,
        is_authenticated=True,
        departamento_user="AGENDAMENTO",
        departamentos_extras=[],
    )
    check_bool(
        "agendamento le concluido no gestao",
        _prodesp_resposta_leitura_concluido(674, ag_gp) is None,
        True,
    )

    impl = SimpleNamespace(
        admin_user=0,
        is_authenticated=True,
        departamento_user="IMPLANTAÇÃO",
        departamentos_extras=[],
        id_user=99,
        nome_user="Analista Teste",
    )
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.fetchone.return_value = ("Concluído",)

    with app.app_context():
        with patch("prodesp.app.get_db_connection", return_value=mock_conn):
            with patch(
                "login.portal_project_access.usuario_pode_leitura_atendimento",
                return_value=(False, "Sem permissão"),
            ):
                denied = _prodesp_resposta_leitura_concluido(674, impl)

    check_bool("implantacao bloqueia concluido alheio", denied is not None, True)
    check_eq("implantacao bloqueia http 404", denied[1], 404)

    with app.app_context():
        with patch("prodesp.app.get_db_connection", return_value=mock_conn):
            with patch(
                "login.portal_project_access.usuario_pode_leitura_atendimento",
                return_value=(True, None),
            ):
                allowed = _prodesp_resposta_leitura_concluido(674, impl)

    check_bool(
        "implantacao le proprio concluido via SEC-005",
        allowed is None,
        True,
    )


def test_mv_opcionais_spec_consistency():
    """Regressão hotfix create: spec MV com max_chars, UPDATE_JS_TO_DB e COLUMN_LIMITS alinhados."""
    from prodesp.prodesp.db_field_limits import (
        UNIDADES_LAN_EXTRA_SPEC,
        UNIDADES_MV_OPCIONAIS_SPEC,
        unidades_lan_extra_update_js_to_db,
        unidades_mv_opcionais_update_js_to_db,
    )
    mv_update = unidades_mv_opcionais_update_js_to_db()
    for js, db_col, csv_hdr, label, max_ch in UNIDADES_MV_OPCIONAIS_SPEC:
        if not js.startswith("mv_"):
            FAILURES.append(f"mv spec js_key invalido: {js}")
        if not db_col.startswith("mv_") or not db_col.endswith("_unidades"):
            FAILURES.append(f"mv spec db_col invalido: {db_col}")
        if not csv_hdr.startswith("MV_"):
            FAILURES.append(f"mv spec csv_hdr invalido: {csv_hdr}")
        if max_ch <= 0:
            FAILURES.append(f"mv spec max_chars invalido: {db_col}={max_ch}")
        if mv_update.get(js) != ("unidades", db_col):
            FAILURES.append(f"mv UPDATE_JS_TO_DB diverge: {js}")
        if UPDATE_JS_TO_DB.get(js) != ("unidades", db_col):
            FAILURES.append(f"mv UPDATE_JS_TO_DB nao registrado: {js}")
        meta = COLUMN_LIMITS.get(("unidades", db_col))
        if not meta or meta[0] != max_ch:
            FAILURES.append(
                f"mv COLUMN_LIMITS diverge: {db_col} spec={max_ch} py={meta[0] if meta else None}"
            )
        for prefix in ("edit", "create"):
            el = f"{prefix}{''.join(p.capitalize() for p in js.split('_'))}"
            if FORM_ELEMENT_LIMITS.get(el) != max_ch:
                FAILURES.append(f"mv FORM_ELEMENT_LIMITS diverge: {el}")
    internal = audit_mv_opcionais_spec()
    for d in internal:
        FAILURES.append(f"mv audit interno: {d}")
    if not internal:
        OK.append(f"mv opcionais: {len(UNIDADES_MV_OPCIONAIS_SPEC)} campos com max_chars no spec")

    lan_update = unidades_lan_extra_update_js_to_db()
    for js, db_col, csv_hdr, _mask, _label, max_ch, kind in UNIDADES_LAN_EXTRA_SPEC:
        if lan_update.get(js) != ("unidades", db_col):
            FAILURES.append(f"lan extra UPDATE_JS_TO_DB diverge: {js}")
        if UPDATE_JS_TO_DB.get(js) != ("unidades", db_col):
            FAILURES.append(f"lan extra UPDATE_JS_TO_DB nao registrado: {js}")
        meta = COLUMN_LIMITS.get(("unidades", db_col))
        if not meta or meta[0] != max_ch:
            FAILURES.append(f"lan extra COLUMN_LIMITS diverge: {db_col}")
        if kind not in ("cidr", "plain"):
            FAILURES.append(f"lan extra kind invalido: {js}={kind}")
        if not csv_hdr.startswith("MV_"):
            FAILURES.append(f"lan extra csv invalido: {csv_hdr}")
        for prefix in ("edit", "create"):
            el = f"{prefix}{''.join(p.capitalize() for p in js.split('_'))}"
            if FORM_ELEMENT_LIMITS.get(el) != max_ch:
                FAILURES.append(f"lan extra FORM_ELEMENT_LIMITS diverge: {el}")
    wifi_in_mv = [js for js, *_ in UNIDADES_MV_OPCIONAIS_SPEC if "wifi" in js]
    if len(wifi_in_mv) < 6:
        FAILURES.append(f"wifi guest incompleto no MV spec: {wifi_in_mv}")
    else:
        OK.append(f"wifi guest: {len(wifi_in_mv)} campos no MV opcionais spec")
    sec_lim = COLUMN_LIMITS.get(("unidades", "mv_ip_lan_sec_unidades"))
    if not sec_lim or sec_lim[0] != 255:
        FAILURES.append("lan sec COLUMN_LIMITS deve ser 255 (legado ip_lan_02)")
    else:
        OK.append("lan sec: limite 255 alinhado ao rename legado")
    OK.append(f"lan extra: {len(UNIDADES_LAN_EXTRA_SPEC)} campos no spec")


def test_schema_alignment_live():
    """Requer banco configurado (mesmo do app). Falha se limites Python != INFORMATION_SCHEMA."""
    try:
        import mysql.connector

        from prodesp.credentials.db_config import db_config

        conn = mysql.connector.connect(**db_config)
        schema = fetch_schema_varchar_limits(conn)
        conn.close()
        divergencias = audit_limits_against_schema(schema)
        if divergencias:
            for d in divergencias:
                FAILURES.append(f"schema audit: {d}")
        else:
            OK.append("schema: COLUMN_LIMITS e FORM alinhados ao INFORMATION_SCHEMA")
    except Exception as exc:
        OK.append(f"schema audit ignorado ({type(exc).__name__})")


def test_create_duplicado_sem_transacao_aninhada():
    """Regressão: create_atendimento já está em transação implícita (autocommit=False)."""
    from unittest.mock import MagicMock

    from prodesp.app import _prodesp_bloquear_create_duplicado_em_atendimento

    conn = MagicMock()
    conn.in_transaction = True
    cur = MagicMock()
    cur.fetchone.side_effect = [{"id_unidades": 1}, None]

    bloqueado, resp, http = _prodesp_bloquear_create_duplicado_em_atendimento(
        cur, conn, 1, "Em Atendimento", HOJE
    )
    conn.start_transaction.assert_not_called()
    check_bool("create dup check nao chama start_transaction", bloqueado, False)
    if resp is not None or http is not None:
        FAILURES.append("create dup check inesperado: bloqueou sem ativo")


def test_agendamento_csv_resumo_e_bloqueio_concluido():
    from prodesp.prodesp.blueprint.agendamento_csv_notifier import (
        AgendamentoCsvRelatorio,
        build_resumo_agendamento_csv,
        build_resumo_from_relatorio,
    )
    from prodesp.app import (
        _prodesp_mensagem_bloqueio_agenda_unidade_concluida,
        _prodesp_status_concluido,
    )

    texto = build_resumo_agendamento_csv(sucessos=44, repetidos=0, erros=0)
    check(
        "csv resumo portal",
        None if "44 unidade(s) agendada(s) com sucesso" in texto else texto,
        expect_fail=False,
    )
    rel = AgendamentoCsvRelatorio(sucessos=[1, 2], repetidos=[3], erros=[4, 5])
    check_bool(
        "csv resumo relatorio",
        build_resumo_from_relatorio(rel)
        == "Resumo: 2 unidade(s) agendada(s) com sucesso · 1 unidade(s) já agendada(s) · 2 unidade(s) não agendada(s)",
        True,
    )
    check_bool("status concluido acento", _prodesp_status_concluido("Concluído"), True)
    check_bool("status concluido sem acento", _prodesp_status_concluido("Concluido"), True)
    check_bool("status quebra nao concluido", _prodesp_status_concluido("Quebra"), False)
    msg = _prodesp_mensagem_bloqueio_agenda_unidade_concluida(date(2026, 6, 15))
    check(
        "csv bloqueio concluido msg",
        None if "15/06/2026" in msg else msg,
        expect_fail=False,
    )
    from prodesp.prodesp.blueprint.agendamento_csv_notifier import (
        LOGO_VITA_CID,
        _logo_vita_img_tag,
        _logo_vita_inline_attachment,
        _logo_vita_path,
    )

    logo = _logo_vita_path()
    check_bool("logo vita assinatura existe", logo is not None and logo.is_file(), True)
    check_bool(
        "logo vita img tag usa cid",
        f'cid:{LOGO_VITA_CID}' in _logo_vita_img_tag() and "font-size:18px" not in _logo_vita_img_tag(),
        True,
    )
    att = _logo_vita_inline_attachment()
    check_bool("logo vita inline attachment", att is not None and att.get("contentId") == LOGO_VITA_CID, True)


def main():
    test_field_limits()
    test_mv_opcionais_spec_consistency()
    test_schema_alignment_live()
    test_create_duplicado_sem_transacao_aninhada()
    test_edicao_perfil()
    test_edicao_observacao_pos_quebra_ag_gp()
    test_edicao_payload_lista_api()
    test_concorrencia_substatus()
    test_transicao_substatus_ag_gp()
    test_agendados_id_vgr()
    test_create_duplicado_agendado()
    test_substatus_pickup_stale_e_filas()
    test_dono_edicao_todas_etapas()
    test_coordenadas_equivalentes()
    test_sanitize_plain_ipv4_field()
    test_dados_field_triagem_para_fila()
    test_colunas_analista_liberar_retorno_fila()
    test_substatus_quebra_normal()
    test_quebra_massa_vincula_observacoes_pre_agendamento()
    test_mysql_lock_wait_timeout_mensagem_amigavel()
    test_implantacao_entrada_aguarda_gestao_permitida()
    test_marcos_atividade_gestao_unificado()
    test_atendimentos_rota_mv_opcionais_template_context()
    test_dt_sync_dismiss_overlays()
    test_dashboard_refresh_unificado()
    test_kpis_tempo_etapa_dashboard()
    test_observacao_substatus_transicao()
    test_hostname_obrigatorio_transicao()
    test_sql_cte_ultimo_substatus_agg()
    test_relatorio_analitico_metricas_etapa()
    test_janela_envio_relatorio_gestao()
    test_relatorio_obs_format_cell()
    test_kpis_relatorio_gestao_email()
    test_leitura_concluido_perfil_gestao()
    test_agendamento_csv_resumo_e_bloqueio_concluido()
    from prodesp.prodesp.tests import test_lan_extra_wifi_scenarios as lan_wifi

    lan_wifi.FAILURES.clear()
    lan_wifi.OK.clear()
    lan_wifi.test_whitelist_create_update_select_blueprint()
    lan_wifi.test_create_edit_payload_vazio_e_preenchido()
    lan_wifi.test_blueprint_parse_persist_vazio_e_preenchido()
    lan_wifi.test_csv_stubs_vazios_e_validacao_opcional()
    lan_wifi.test_js_create_edit_details_keys()
    for x in lan_wifi.OK:
        OK.append(f"lan_wifi: {x}")
    for x in lan_wifi.FAILURES:
        FAILURES.append(f"lan_wifi: {x}")

    print("=== OK (%d) ===" % len(OK))
    for x in OK:
        try:
            print(" ", x)
        except UnicodeEncodeError:
            print(" ", x.encode("ascii", "replace").decode("ascii"))
    print("=== FALHAS / LACUNAS (%d) ===" % len(FAILURES))
    for x in FAILURES:
        try:
            print(" ", x)
        except UnicodeEncodeError:
            print(" ", x.encode("ascii", "replace").decode("ascii"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
