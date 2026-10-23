"""Personalização dos reports: validação, agenda, condicionais e envio do Macro/FUST."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from core.reports import report_settings as rs
from core.reports.kpi_macro import KpiMacro
from core.reports.report_settings import (
    ENVIADO,
    carregar_config,
    executar_tick,
    final_devido,
    fingerprint,
    normalizar_config,
    omitido,
    slot_periodico,
)

def _dt(texto: str) -> datetime:
    return datetime.strptime(texto, "%Y-%m-%d %H:%M")


@pytest.fixture
def env_macro(monkeypatch):
    monkeypatch.setenv("SUPERVISORES_MACRO_EMAIL_ENABLED", "true")
    monkeypatch.setenv("SUPERVISORES_MACRO_TEAMS_ENABLED", "true")
    monkeypatch.setenv("SUPERVISORES_MACRO_EMAIL_TO", "a@x.com;b@x.com")
    monkeypatch.delenv("SUPERVISORES_MACRO_HORA_INICIO", raising=False)
    monkeypatch.delenv("SUPERVISORES_MACRO_HORA_FIM", raising=False)
    monkeypatch.delenv("SUPERVISORES_MACRO_SKIP_VAZIO", raising=False)


# ---------------------------------------------------------------- config / validação


def test_padrao_vem_do_env(env_macro):
    cfg = carregar_config("MACRO")
    assert cfg.hora_inicio == "10:00" and cfg.hora_fim == "18:00"
    assert cfg.emails_to == ["a@x.com", "b@x.com"]
    assert cfg.email_ativo and cfg.teams_ativo
    assert cfg.dias_semana == [0, 1, 2, 3, 4]
    assert not rs.tem_override("MACRO")


def test_override_kvs_sobrepoe_env(env_macro, kvs_fake):
    base = carregar_config("MACRO")
    cfg, erros = normalizar_config(
        "MACRO",
        {"hora_inicio": "08:30", "intervalo_min": 90, "emails_cc": "c@x.com", "teams_enabled": False},
        base=base,
    )
    assert erros == []
    rs.salvar_config(cfg)
    assert "REPORT_CFG_MACRO" in kvs_fake
    lido = carregar_config("MACRO")
    assert lido.hora_inicio == "08:30"
    assert lido.intervalo_min == 90
    assert lido.emails_cc == ["c@x.com"]
    assert lido.teams_ativo is False
    rs.restaurar_padrao("MACRO")
    assert carregar_config("MACRO").hora_inicio == "10:00"


@pytest.mark.parametrize(
    "payload, trecho",
    [
        ({"hora_inicio": "25:00"}, "hora_inicio"),
        ({"hora_inicio": "19:00", "hora_fim": "18:00"}, "menor ou igual"),
        ({"intervalo_min": 2}, "intervalo_min"),
        ({"intervalo_min": "abc"}, "intervalo_min"),
        ({"dias_semana": []}, "dia da semana"),
        ({"feriados": "2026-02-30"}, "feriados"),
        ({"emails_to": "nao-e-email"}, "emails_to"),
        ({"emails_to": ""}, "sem destinatário"),
    ],
)
def test_validacao_rejeita_campos_invalidos(env_macro, payload, trecho):
    _cfg, erros = normalizar_config("MACRO", payload, base=carregar_config("MACRO"))
    assert any(trecho in e for e in erros), erros


def test_feriados_aceitam_padrao_brasileiro(env_macro):
    cfg, erros = normalizar_config(
        "MACRO", {"feriados": "20-11-2026; 02/11/2026\n2026-12-25"}, base=carregar_config("MACRO")
    )
    assert erros == []
    assert cfg.feriados == ["2026-11-02", "2026-11-20", "2026-12-25"]
    for invalida in ("31-02-2026", "2026/11/20", "20-11-26", "20-11/2026"):
        _cfg, erros = normalizar_config("MACRO", {"feriados": invalida}, base=carregar_config("MACRO"))
        assert any("DD-MM-AAAA" in e for e in erros), invalida


def test_emails_com_injecao_de_cabecalho_sao_rejeitados(env_macro):
    _cfg, erros = normalizar_config(
        "MACRO", {"emails_to": ["a@x.com\r\nBcc: z@y.com"]}, base=carregar_config("MACRO")
    )
    assert erros


def test_canal_inexistente_no_report_fica_desligado(monkeypatch):
    monkeypatch.setenv("SUPERVISORES_MACRO_TEAMS_ENABLED", "true")
    cfg, erros = normalizar_config("FUST", {"email_enabled": True, "emails_to": "a@x.com"})
    assert erros == []
    assert cfg.email_enabled is False and cfg.emails_to == []


def test_override_corrompido_no_kvs_cai_no_env(env_macro, kvs_fake):
    kvs_fake["REPORT_CFG_MACRO"] = "{nao é json"
    assert carregar_config("MACRO").hora_inicio == "10:00"
    kvs_fake["REPORT_CFG_MACRO"] = json.dumps({"hora_inicio": "99:99", "intervalo_min": 60})
    cfg = carregar_config("MACRO")
    assert cfg.hora_inicio == "10:00"
    assert cfg.intervalo_min == 60


# ---------------------------------------------------------------- agenda


def test_slot_intervalo_e_final_preservam_comportamento_antigo(env_macro):
    cfg = carregar_config("MACRO")  # 10:00–18:00, 30 min, Final às 18:00
    assert slot_periodico(cfg, _dt("2026-10-14 09:59")) is None
    assert slot_periodico(cfg, _dt("2026-10-14 10:00")) == "2026-10-14 #0"
    assert slot_periodico(cfg, _dt("2026-10-14 10:29")) == "2026-10-14 #0"
    assert slot_periodico(cfg, _dt("2026-10-14 10:30")) == "2026-10-14 #1"
    assert slot_periodico(cfg, _dt("2026-10-14 18:00")) == "2026-10-14 #16"
    assert slot_periodico(cfg, _dt("2026-10-14 18:01")) is None
    assert not final_devido(cfg, _dt("2026-10-14 18:00"))
    assert final_devido(cfg, _dt("2026-10-14 18:01"))


def test_intervalo_custom_e_final_antecipado(env_macro):
    cfg, _ = normalizar_config(
        "MACRO", {"intervalo_min": 45, "final_hora": "16:00"}, base=carregar_config("MACRO")
    )
    assert slot_periodico(cfg, _dt("2026-10-14 10:44")) == "2026-10-14 #0"
    assert slot_periodico(cfg, _dt("2026-10-14 10:45")) == "2026-10-14 #1"
    # periódicos param no horário do Final
    assert slot_periodico(cfg, _dt("2026-10-14 16:01")) is None
    assert final_devido(cfg, _dt("2026-10-14 16:01"))


def test_dias_semana_e_feriados(env_macro):
    cfg, _ = normalizar_config(
        "MACRO", {"feriados": "2026-10-12"}, base=carregar_config("MACRO")
    )
    assert slot_periodico(cfg, _dt("2026-10-12 11:00")) is None  # feriado (segunda)
    assert slot_periodico(cfg, _dt("2026-10-17 11:00")) is None  # sábado
    assert not final_devido(cfg, _dt("2026-10-17 19:00"))
    assert slot_periodico(cfg, _dt("2026-10-13 11:00")) is not None


def test_tbra_horarios_fixos(monkeypatch):
    monkeypatch.delenv("PRODESP_TIME_TBRA_RELATORIO_HORARIOS", raising=False)
    cfg = carregar_config("TBRA")
    assert cfg.agenda_modo == "horarios"
    assert cfg.horarios == ["11:00", "15:00", "18:00", "22:00"]
    assert slot_periodico(cfg, _dt("2026-10-14 10:59")) is None
    assert slot_periodico(cfg, _dt("2026-10-14 11:00")) == "2026-10-14 H11:00"
    assert slot_periodico(cfg, _dt("2026-10-14 11:59")) == "2026-10-14 H11:00"
    assert slot_periodico(cfg, _dt("2026-10-14 12:00")) is None
    assert not final_devido(cfg, _dt("2026-10-14 22:00"))
    assert final_devido(cfg, _dt("2026-10-14 22:01"))
    cfg2, erros = normalizar_config("TBRA", {"agenda_modo": "intervalo", "intervalo_min": 120}, base=cfg)
    assert erros == [] and cfg2.agenda_modo == "intervalo"


@pytest.mark.parametrize("report_id", rs.REPORT_IDS)
def test_todos_aceitam_horarios_fixos(monkeypatch, report_id):
    monkeypatch.setenv("SUPERVISORES_MACRO_TEAMS_ENABLED", "true")
    monkeypatch.setenv("SUPERVISORES_MACRO_EMAIL_TO", "a@x.com")
    assert rs.SPECS[report_id].agenda_horarios is True
    cfg, erros = normalizar_config(
        report_id, {"agenda_modo": "horarios", "horarios": "09:00; 13:30"}, base=carregar_config(report_id)
    )
    assert erros == [] and cfg.agenda_modo == "horarios"
    _cfg, erros = normalizar_config(report_id, {"agenda_modo": "horarios", "horarios": ""}, base=cfg)
    assert any("horário fixo" in e for e in erros)


def test_macro_horarios_fixos_e_final(env_macro):
    cfg, _ = normalizar_config(
        "MACRO",
        {"agenda_modo": "horarios", "horarios": "09:00; 13:30", "final_hora": "17:00"},
        base=carregar_config("MACRO"),
    )
    assert slot_periodico(cfg, _dt("2026-10-14 08:59")) is None
    assert slot_periodico(cfg, _dt("2026-10-14 09:00")) == "2026-10-14 H09:00"
    assert slot_periodico(cfg, _dt("2026-10-14 13:45")) == "2026-10-14 H13:30"
    assert slot_periodico(cfg, _dt("2026-10-14 15:00")) is None
    assert not final_devido(cfg, _dt("2026-10-14 16:59"))
    assert final_devido(cfg, _dt("2026-10-14 17:00"))


def test_fila_horarios_fixos_relembra_so_no_horario(monkeypatch, kvs_fake):
    import core.reports.data_loaders as dl
    import core.reports.send_reports as sr
    from core.reports.fila_sem_analista import FilaEsperaItem
    from core.reports.scheduler import tick_fila

    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_ENABLED", "true")
    cfg, erros = normalizar_config(
        "FILA",
        {"agenda_modo": "horarios", "horarios": "10:00; 14:00", "final_enabled": False},
        base=carregar_config("FILA"),
    )
    assert erros == []
    rs.salvar_config(cfg)

    def item(n):
        return FilaEsperaItem("PRODESP", n, str(n), "U", "SP", "SP", None, 3600, "", "", 0, 0)

    fila = [item(1)]
    monkeypatch.setattr(dl, "carregar_fila_atual", lambda minutos_min=30: list(fila))
    envios = []
    monkeypatch.setattr(sr, "enviar_fila", lambda tipo, itens=None: envios.append(len(itens or [])) or ENVIADO)
    estado: dict = {"contagem": {}}

    tick_fila(_dt("2026-10-14 08:00"), estado)  # unidade nova: alerta na hora
    tick_fila(_dt("2026-10-14 09:00"), estado)  # mesma fila, fora do horário fixo
    assert envios == [1]
    tick_fila(_dt("2026-10-14 10:00"), estado)  # horário fixo: relembra
    tick_fila(_dt("2026-10-14 10:30"), estado)
    assert envios == [1, 1]
    fila.append(item(2))
    tick_fila(_dt("2026-10-14 11:00"), estado)  # nova unidade fora do horário fixo
    assert envios == [1, 1, 2]
    tick_fila(_dt("2026-10-14 14:05"), estado)
    assert envios == [1, 1, 2, 2]


def test_fila_final_nao_encerra_alertas(monkeypatch):
    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_ENABLED", "true")
    monkeypatch.delenv("SUPERVISORES_FILA_SEMPRE", raising=False)
    monkeypatch.delenv("SUPERVISORES_FILA_HORA_FIM", raising=False)
    cfg = carregar_config("FILA")
    assert cfg.hora_inicio == "00:00" and cfg.hora_fim == "23:59"
    assert rs.dentro_janela(cfg, _dt("2026-10-14 21:00"))
    assert final_devido(cfg, _dt("2026-10-14 19:00"))


# ---------------------------------------------------------------- tick


def test_tick_envia_uma_vez_por_slot_e_final_uma_vez_por_dia(env_macro):
    chamadas = []
    estado: dict = {}

    def per():
        chamadas.append("p")
        return ENVIADO

    def fin():
        chamadas.append("f")
        return ENVIADO

    for hora in ("10:00", "10:10", "10:31", "18:01", "18:30", "19:00"):
        executar_tick("MACRO", _dt(f"2026-10-14 {hora}"), estado, per, fin)
    assert chamadas == ["p", "p", "f"]
    executar_tick("MACRO", _dt("2026-10-15 10:00"), estado, per, fin)
    assert chamadas == ["p", "p", "f", "p"]


def test_tick_falha_tenta_de_novo_no_mesmo_slot(env_macro):
    estado: dict = {}
    respostas = [omitido("falha"), ENVIADO]
    chamadas = []

    def per():
        chamadas.append(1)
        return respostas.pop(0)

    executar_tick("MACRO", _dt("2026-10-14 10:00"), estado, per, lambda: ENVIADO)
    executar_tick("MACRO", _dt("2026-10-14 10:01"), estado, per, lambda: ENVIADO)
    executar_tick("MACRO", _dt("2026-10-14 10:02"), estado, per, lambda: ENVIADO)
    assert len(chamadas) == 2


def test_tick_dia_encerrado_dispara_final_na_hora(env_macro):
    estado: dict = {}
    finais = []
    executar_tick(
        "MACRO",
        _dt("2026-10-14 15:00"),
        estado,
        lambda: omitido("encerrado"),
        lambda: finais.append(1) or ENVIADO,
    )
    assert finais == [1]
    executar_tick("MACRO", _dt("2026-10-14 18:05"), estado, lambda: ENVIADO, lambda: finais.append(1) or ENVIADO)
    assert finais == [1]


def test_tick_final_pendente_tenta_novamente(env_macro):
    estado: dict = {}
    respostas = [omitido("pendente"), ENVIADO]
    for hora in ("18:01", "18:02", "18:03"):
        executar_tick("MACRO", _dt(f"2026-10-14 {hora}"), estado, lambda: ENVIADO, lambda: respostas.pop(0) if respostas else pytest.fail("Final repetido"))
    assert respostas == []


def test_tick_report_desabilitado_nao_chama_envio(env_macro, kvs_fake):
    cfg, _ = normalizar_config("MACRO", {"enabled": False}, base=carregar_config("MACRO"))
    rs.salvar_config(cfg)
    executar_tick("MACRO", _dt("2026-10-14 10:00"), {}, lambda: pytest.fail("enviou"), lambda: pytest.fail("enviou"))


# ---------------------------------------------------------------- fingerprint


def test_fingerprint_ignora_tempo_medio_e_compara_numeros():
    a = KpiMacro(total=26, agendados=26, tempo_medio="00:10:00")
    b = KpiMacro(total=26, agendados=26, tempo_medio="00:20:00")
    c = KpiMacro(total=26, agendados=25, com_atividade=1, em_atendimento=1)
    assert fingerprint(a, None) == fingerprint(b, None)
    assert fingerprint(a, None) != fingerprint(c, None)


# ---------------------------------------------------------------- envio Macro / FUST


@pytest.fixture
def macro_fake(monkeypatch, env_macro):
    import core.reports.send_reports as sr

    kpis = {"PRODESP": KpiMacro(), "FUST": KpiMacro()}
    enviados: dict[str, list] = {"email": [], "teams": [], "fust": []}
    monkeypatch.setattr(sr, "_carregar_kpis_macro", lambda s, e: (kpis["PRODESP"], kpis["FUST"]))
    monkeypatch.setattr(
        sr,
        "_enviar_email",
        lambda subject, html_body, recipients, log_label, cc=None: enviados["email"].append(
            (subject, html_body, list(recipients), list(cc or []))
        )
        or True,
    )
    monkeypatch.setattr(sr, "teams_webhook_url", lambda: "https://macro.example/hook")
    monkeypatch.setattr(sr, "teams_channel_email", lambda: "")
    monkeypatch.setattr(
        sr,
        "send_teams_webhook",
        lambda **kw: enviados["fust" if kw.get("webhook_url") else "teams"].append(kw) or True,
    )
    return kpis, enviados


def test_macro_sem_dados_nao_envia(macro_fake):
    from core.reports.send_reports import enviar_macro

    _kpis, enviados = macro_fake
    res = enviar_macro(tipo="periodico")
    assert res.motivo == "sem_dados"
    assert enviados["email"] == [] and enviados["teams"] == []


def test_macro_envia_so_o_projeto_com_dados(macro_fake):
    from core.reports.send_reports import enviar_macro

    kpis, enviados = macro_fake
    kpis["FUST"] = KpiMacro(total=5, agendados=5)
    res = enviar_macro(tipo="periodico")
    assert res.enviado
    subject, html_body, to, cc = enviados["email"][0]
    assert "FUST" in subject and "PRODESP" not in subject
    assert "PRODESP</h3>" not in html_body and "<strong>PRODESP</strong>" not in html_body
    assert "FUST</h3>" in html_body
    assert to == ["a@x.com", "b@x.com"] and cc == []
    assert enviados["teams"] and enviados["fust"] == []


def test_macro_nao_reenvia_dados_iguais(macro_fake, kvs_fake):
    from core.reports.send_reports import enviar_macro

    kpis, enviados = macro_fake
    cfg, _ = normalizar_config("MACRO", {"skip_igual": True, "emails_cc": "c@x.com"}, base=carregar_config("MACRO"))
    rs.salvar_config(cfg)
    kpis["PRODESP"] = KpiMacro(total=26, agendados=26)
    assert enviar_macro(tipo="periodico").enviado
    assert enviados["email"][0][3] == ["c@x.com"]
    assert enviar_macro(tipo="periodico").motivo == "igual"
    kpis["PRODESP"] = KpiMacro(total=26, agendados=25, com_atividade=1, em_atendimento=1)
    assert enviar_macro(tipo="periodico").enviado
    assert len(enviados["email"]) == 2
    # o Final não é bloqueado pelo "igual"
    assert enviar_macro(tipo="final").enviado


def test_macro_dia_encerrado_e_final_so_com_atividade(macro_fake, kvs_fake):
    from core.reports.send_reports import enviar_macro

    kpis, _enviados = macro_fake
    cfg, _ = normalizar_config(
        "MACRO",
        {"parar_dia_encerrado": True, "final_so_com_atividade": True},
        base=carregar_config("MACRO"),
    )
    rs.salvar_config(cfg)
    kpis["PRODESP"] = KpiMacro(total=10, agendados=4, com_atividade=6, em_atendimento=0, concluidos=6)
    assert enviar_macro(tipo="periodico").motivo == "encerrado"
    kpis["PRODESP"] = KpiMacro(total=10, agendados=10)
    assert enviar_macro(tipo="final").motivo == "sem_atividade"


def test_fust_only_tem_config_propria(monkeypatch, kvs_fake):
    import core.reports.send_reports as sr

    monkeypatch.setenv("SUPERVISORES_MACRO_TEAMS_ENABLED", "true")
    monkeypatch.setattr(sr, "teams_fust_webhook_url", lambda: "https://fust.example/hook")
    monkeypatch.setattr(sr, "carregar_rows_fust", lambda s, e: [])
    monkeypatch.setattr(sr, "carregar_kpis_resumo_supervisao_dia", lambda d: {})
    monkeypatch.setattr(sr, "calcular_kpis_fust", lambda rows, resumo_kpi=None: KpiMacro(total=3, agendados=3))
    posts = []
    monkeypatch.setattr(sr, "send_teams_webhook", lambda **kw: posts.append(kw) or True)
    assert sr.enviar_fust(tipo="periodico").enviado
    assert posts[0]["webhook_url"] == "https://fust.example/hook"
    cfg, _ = normalizar_config("FUST", {"teams_enabled": False}, base=carregar_config("FUST"))
    rs.salvar_config(cfg)
    assert sr.enviar_fust(tipo="periodico").motivo == "desabilitado"
    assert len(posts) == 1
