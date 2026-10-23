"""Relatórios SUPERVISORES (macro FUST+PRODESP e fila sem analista)."""
from __future__ import annotations

from datetime import datetime

from core.reports.email_html import (
    build_fila_email_html,
    build_macro_email_html,
    build_macro_teams_card,
    build_macro_teams_text,
)
from core.reports.env_config import (
    DEFAULT_SUPERVISORES_FILA_TO,
    DEFAULT_SUPERVISORES_MACRO_TO,
    parse_recipients,
)
from core.reports.fila_sem_analista import (
    FilaEsperaItem,
    TZ_SP,
    aplicar_proximo_aviso,
    deve_enviar_snapshot_fila,
    filtrar_fila_atual,
    intervalos_fila_do_log,
    itens_ainda_nao_alertados,
    itens_final_do_log,
    podar_contagem_avisos,
    registrar_envio_avisos,
)
from core.reports.kpi_macro import calcular_kpis_fust, calcular_kpis_prodesp
from core.reports.teams_notify import (
    build_teams_webhook_payload,
    is_power_automate_webhook,
    send_teams_webhook,
)


def test_kpis_prodesp_sem_contratada():
    rows = [
        {"id_atendimento": None, "status_atendimentos": "Agendado"},
        {
            "id_atendimentos": 1,
            "status_atendimentos": "Em Atendimento",
            "substatus_atendimentos": "Aguardando Config. Remota",
            "tempo_em_segundos": 120,
        },
        {
            "id_atendimentos": 2,
            "status_atendimentos": "Concluído",
            "substatus_atendimentos": "Concluído",
            "tempo_em_segundos": 3600,
        },
    ]
    resumo = {
        "tempo_medio_seg": 3600,
        "tempo_medio_total_seg": 1860,
        "em_config_remota_cnt": 3,
        "aguardando_caderno_cnt": 2,
        "em_caderno_cnt": 4,
    }
    kpi = calcular_kpis_prodesp(rows, resumo_kpi=resumo)
    assert kpi.agendados == 1
    assert kpi.em_atendimento == 1
    assert kpi.aguardando_remota == 1
    assert kpi.concluidos == 1
    assert kpi.total == 3
    assert kpi.tempo_medio == "00:31:00"
    assert kpi.em_config_remota_cnt == 3
    assert kpi.aguardando_caderno_cnt == 2
    assert kpi.em_caderno_painel_cnt == 4


def test_kpis_fust_catalogo():
    rows = [
        {"status_atendimentos": "Agendado"},
        {
            "id_atendimentos": 10,
            "status_atendimentos": "Em Atendimento",
            "substatus_atendimentos": "Aguarda Gestão",
            "tempo_em_segundos": 60,
        },
        {
            "id_atendimentos": 11,
            "status_atendimentos": "Em Atendimento",
            "substatus_atendimentos": "Em Caderno de Teste",
            "tempo_em_segundos": 300,
        },
        {
            "id_atendimentos": 12,
            "status_atendimentos": "Concluido",
            "substatus_atendimentos": "Concluido",
            "tempo_em_segundos": 7200,
        },
    ]
    kpi = calcular_kpis_fust(rows)
    assert kpi.agendados == 1
    assert kpi.aguarda_gestao == 1
    assert kpi.em_caderno == 1
    assert kpi.concluidos == 1
    assert kpi.aguarda_licenca == 0
    assert kpi.quebra_tbra == 0
    assert kpi.tempo_medio == "00:42:00"
    kpi2 = calcular_kpis_fust(
        rows,
        resumo_kpi={
            "tempo_medio_seg": 7200,
            "tempo_medio_total_seg": 2520,
            "em_config_remota_cnt": 5,
            "aguardando_caderno_cnt": 4,
            "em_caderno_cnt": 6,
        },
    )
    assert kpi2.tempo_medio == "00:42:00"
    assert kpi2.em_config_remota_cnt == 5
    assert kpi2.aguardando_caderno_cnt == 4
    assert kpi2.em_caderno_painel_cnt == 6


def test_spec_cards_tem_kpis_novos():
    from core.reports.kpi_macro import KpiMacro, spec_cards_fust, spec_cards_prodesp

    kpi = KpiMacro(
        total=1,
        tempo_medio="01:01:01",
        em_config_remota_cnt=3,
        aguardando_caderno_cnt=2,
        em_caderno_painel_cnt=5,
    )
    cards_f = {c[0]: (c[1], c[2]) for c in spec_cards_fust(kpi)}
    cards_p = {c[0]: (c[1], c[2]) for c in spec_cards_prodesp(kpi)}
    assert cards_f["Em Config Remota"] == ("3", "3 substatus (painel)")
    assert cards_f["Aguard. Caderno"] == ("2", "Fila caderno (painel)")
    assert cards_f["Em Caderno"] == ("5", "Etapa caderno (painel)")
    assert "Em Etapa Caderno / Aguardando" not in cards_f
    assert "Em Configuração Remota" not in cards_f
    assert "Aguardando Caderno de Teste" not in cards_f
    assert "Em Caderno de Teste" not in cards_f
    assert (
        cards_f["Tempo médio"][1]
        == "Média (todos c/ ativ.)"
    )
    assert cards_p["Em Config Remota"] == ("3", "3 substatus (painel)")
    assert cards_p["Aguard. Caderno"] == ("2", "Fila caderno (painel)")
    assert cards_p["Em Caderno"] == ("5", "Etapa caderno (painel)")
    assert "Em Etapa Caderno / Aguardando" not in cards_p
    assert cards_p["Aguard. Config."] == (str(kpi.aguardando_remota), "Fila remota")
    assert cards_p["Total período"] == ("1", f"{kpi.agendados} agend. + {kpi.com_atividade} ativos")


def test_html_macro_nao_tem_contratada_nem_anexo():
    from core.reports.kpi_macro import KpiMacro

    html = build_macro_email_html(
        periodo_label="14/09/2026",
        gerado_em="14/09/2026 10:00",
        kpi_prodesp=KpiMacro(total=2, agendados=1, com_atividade=1),
        kpi_fust=KpiMacro(total=3, agendados=1, com_atividade=2, concluidos=1),
    )
    assert "PRODESP" in html
    assert "FUST" in html
    assert "Resumo por contratada" not in html
    assert "anexo XLSX" not in html
    assert ".xlsx" not in html.lower()


def test_fila_filtra_30_min_sem_analista():
    agora = TZ_SP.localize(datetime(2026, 9, 14, 12, 0, 0))
    itens = [
        FilaEsperaItem("FUST", 1, "35071225", "Escola A", "SP", "SP", agora, 29 * 60, ""),
        FilaEsperaItem("PRODESP", 2, "VGR1", "Unidade B", "Campinas", "SP", agora, 31 * 60, ""),
        FilaEsperaItem("FUST", 3, "1", "Escola C", "X", "SP", agora, 40 * 60, "Ana"),
    ]
    ok = filtrar_fila_atual(itens, minutos_min=30)
    assert [i.id_atendimento for i in ok] == [2]


def test_intervalos_e_final_quem_atendeu():
    eventos = [
        {
            "valor_novo_log": "Aguardando Config. Remota",
            "alterado_em_log": "2026-09-14 10:00:00",
            "usuario_log": "",
        },
        {
            "valor_novo_log": "Em Configuração Remota",
            "alterado_em_log": "2026-09-14 10:45:00",
            "usuario_log": "Ana Silva",
        },
    ]
    trechos = intervalos_fila_do_log(eventos)
    assert len(trechos) == 1
    assert trechos[0][2] == "Ana Silva"
    itens = itens_final_do_log(
        projeto="FUST",
        id_atendimento=9,
        chave="35071225",
        unidade="Escola X",
        municipio="SP",
        uf="SP",
        analista_atual="Ana Silva",
        eventos=eventos,
        minutos_min=30,
    )
    assert len(itens) == 1
    assert itens[0].espera_seg == 45 * 60
    assert itens[0].analista == "Ana Silva"


def test_html_fila_usa_textos_escapados():
    item = FilaEsperaItem(
        "FUST",
        1,
        "35071225",
        "<script>",
        "SP",
        "SP",
        None,
        3600,
        "Ana",
    )
    html = build_fila_email_html(
        gerado_em="14/09/2026 12:00",
        itens=[item],
        minutos_min=30,
        tipo="periodico",
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "01:00:00" in html
    item.avisos = 3
    html2 = build_fila_email_html(
        gerado_em="14/09/2026 12:15",
        itens=[item],
        minutos_min=30,
        tipo="periodico",
    )
    assert "3ª vez" in html2
    assert "Avisos" in html2


def test_recipients_parse():
    got = parse_recipients("a@x.com; b@x.com,c@x.com")
    assert got == ["a@x.com", "b@x.com", "c@x.com"]


def test_destinatarios_macro_so_supervisores_portal_e_caq():
    assert DEFAULT_SUPERVISORES_MACRO_TO == [
        "felipe.paixao@telefonica.com",
        "alexandre.neves@telefonica.com",
        "caq.vita.br@telefonica.com",
    ]
    assert "jefferson.ccosta@telefonica.com" not in DEFAULT_SUPERVISORES_MACRO_TO
    assert "jefferson.ccosta@telefonica.com" in DEFAULT_SUPERVISORES_FILA_TO
    assert "caq.vita.br@telefonica.com" in DEFAULT_SUPERVISORES_FILA_TO


def test_fila_alerta_so_unidades_novas():
    agora = TZ_SP.localize(datetime(2026, 9, 14, 22, 0, 0))
    a = FilaEsperaItem("FUST", 1, "1", "A", "SP", "SP", agora, 40 * 60, "")
    b = FilaEsperaItem("PRODESP", 2, "2", "B", "SP", "SP", agora, 31 * 60, "")
    novos, vigentes = itens_ainda_nao_alertados([a, b], {("FUST", 1)})
    assert [i.id_atendimento for i in novos] == [2]
    assert vigentes == {("FUST", 1)}
    novos2, vigentes2 = itens_ainda_nao_alertados([b], {("FUST", 1), ("PRODESP", 2)})
    assert novos2 == []
    assert vigentes2 == {("PRODESP", 2)}


def test_snapshot_fila_inclui_ja_avisadas_e_conta_vezes():
    t0 = TZ_SP.localize(datetime(2026, 9, 14, 15, 0, 0))
    t15 = TZ_SP.localize(datetime(2026, 9, 14, 15, 15, 0))
    t20 = TZ_SP.localize(datetime(2026, 9, 14, 15, 20, 0))
    y = FilaEsperaItem("FUST", 1, "Y", "Unidade Y", "SP", "SP", t0, 40 * 60, "")
    x = FilaEsperaItem("PRODESP", 2, "X", "Unidade X", "SP", "SP", t15, 31 * 60, "")
    contagem: dict[tuple[str, int], int] = {}

    assert deve_enviar_snapshot_fila([y], contagem, t0, None, relembre_min=15) is True
    aplicar_proximo_aviso([y], contagem)
    assert y.avisos == 1
    registrar_envio_avisos(contagem, [y])
    assert contagem[("FUST", 1)] == 1

    assert deve_enviar_snapshot_fila([y], contagem, t0, t0, relembre_min=15) is False
    assert deve_enviar_snapshot_fila([y, x], contagem, t15, t0, relembre_min=15) is True
    aplicar_proximo_aviso([y, x], contagem)
    assert y.avisos == 2
    assert x.avisos == 1
    registrar_envio_avisos(contagem, [y, x])

    assert deve_enviar_snapshot_fila([y, x], contagem, t20, t15, relembre_min=15) is False
    t30 = TZ_SP.localize(datetime(2026, 9, 14, 15, 30, 0))
    assert deve_enviar_snapshot_fila([y, x], contagem, t30, t15, relembre_min=15) is True

    so_x = podar_contagem_avisos(contagem, [x])
    assert ("FUST", 1) not in so_x
    assert so_x[("PRODESP", 2)] == 1
    x2 = FilaEsperaItem("PRODESP", 2, "X", "Unidade X", "SP", "SP", t30, 50 * 60, "")
    aplicar_proximo_aviso([x2], so_x)
    assert x2.avisos == 2


def test_teams_text_tem_fust_e_prodesp():
    from core.reports.kpi_macro import KpiMacro

    txt = build_macro_teams_text(
        periodo_label="14/09/2026",
        kpi_prodesp=KpiMacro(total=10, em_atendimento=4, concluidos=2),
        kpi_fust=KpiMacro(total=5, aguardando_remota=1),
    )
    assert "PRODESP" in txt
    assert "FUST" in txt
    assert "14/09/2026" in txt


def test_teams_webhook_rejeita_http():
    assert send_teams_webhook("t", "x", webhook_url="http://evil.example/hook") is False


def test_power_automate_usa_adaptive_card_na_raiz_e_no_attachment():
    url = (
        "https://example.environment.api.powerplatform.com/powerautomate/"
        "automations/direct/workflows/abc/triggers/manual/paths/invoke"
    )
    assert is_power_automate_webhook(url) is True
    payload = build_teams_webhook_payload("Titulo KPI", "**FUST** — 1", url)
    assert payload["type"] == "AdaptiveCard"
    assert payload["body"][0]["text"] == "Titulo KPI"
    card = payload["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.2"
    assert "**FUST**" in card["body"][1]["text"]


def test_incoming_webhook_legado_usa_message_card():
    url = "https://outlook.office.com/webhook/abc/IncomingWebhook/xyz"
    assert is_power_automate_webhook(url) is False
    payload = build_teams_webhook_payload("Titulo", "texto", url)
    assert payload["@type"] == "MessageCard"
    assert payload["title"] == "Titulo"


def test_teams_card_usa_grade_do_email():
    from core.reports.kpi_macro import KpiMacro

    kpi_p = KpiMacro(total=10, agendados=3, em_atendimento=4, concluidos=2, pct_concluidos=20)
    kpi_f = KpiMacro(
        total=5,
        aguardando_remota=1,
        em_caderno=2,
        concluidos=1,
        em_config_remota_cnt=1,
        aguardando_caderno_cnt=1,
        em_caderno_painel_cnt=3,
        tempo_medio="01:00:00",
    )
    card = build_macro_teams_card(
        title="[SUPERVISORES] FUST + PRODESP",
        periodo_label="14/09/2026",
        gerado_em="14/09/2026 23:30",
        kpi_prodesp=kpi_p,
        kpi_fust=kpi_f,
    )
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.2"
    kinds = [b.get("type") for b in card["body"]]
    assert kinds.count("ColumnSet") >= 2
    blob = str(card)
    assert "PRODESP" in blob
    assert "FUST" in blob
    assert "contratada" in blob.lower()
    assert "Em Caderno" in blob
    assert "Quebra TBRA" in blob
    assert "8px" not in blob
    assert "good" in blob
    assert "Em Config Remota" in blob
    assert "Aguard. Caderno" in blob
    assert "Em Caderno" in blob
    assert "Em Etapa Caderno / Aguardando" not in blob
    assert "Em Configuração Remota" not in blob
    grid = next(b for b in card["body"] if b.get("type") == "ColumnSet")
    assert len(grid["columns"]) == 2
    url = "https://example.environment.api.powerautomate.com/powerautomate/x"
    payload = build_teams_webhook_payload("t", "x", url, card=card)
    assert payload["attachments"][0]["content"]["body"] == card["body"]
    assert payload["body"] != card["body"]
    assert payload["type"] == "AdaptiveCard"


def test_blacklist_analista_por_nome_e_email():
    from core.reports.analistas_disponiveis import filtrar_analistas_disponiveis, token_na_blacklist

    assert token_na_blacklist("Rodrigo Xavier Carvalho", "r@x.com", ["Rodrigo Xavier Carvalho"])
    assert token_na_blacklist(
        "Thiago Moraes Silva", "thiago.moraes@telefonica.com", ["thiago.moraes@telefonica.com"]
    )
    assert not token_na_blacklist("Gustavo Serra", "g@x.com", ["Rodrigo Xavier Carvalho"])
    users = [
        {
            "nome_user": "Ana Livre",
            "email_user": "ana@x.com",
            "departamento_user": "IMPLANTAÇÃO",
            "usuario_desabilitado_user": 0,
            "nome_status_disponibilidade": "Disponível",
            "is_online": True,
        },
        {
            "nome_user": "Rodrigo Xavier Carvalho",
            "email_user": "rodrigo@x.com",
            "departamento_user": "IMPLANTAÇÃO",
            "usuario_desabilitado_user": 0,
        },
        {
            "nome_user": "Bruno Ocupado",
            "email_user": "bruno@x.com",
            "departamento_user": "IMPLANTAÇÃO",
            "usuario_desabilitado_user": 0,
        },
        {
            "nome_user": "Carla Extra",
            "email_user": "carla@x.com",
            "departamento_user": "GP",
            "usuario_desabilitado_user": 0,
        },
    ]
    contagens = {
        "Bruno Ocupado": {"em_andamento": 2, "finalizado": 0},
        "Ana Livre": {"em_andamento": 0, "finalizado": 4},
    }
    got = filtrar_analistas_disponiveis(
        users, contagens, ["Rodrigo Xavier Carvalho"], dept_principal="IMPLANTAÇÃO"
    )
    assert [a.nome for a in got] == ["Ana Livre"]
    assert got[0].status_label == "Disponível"
    assert got[0].plataforma_label == "Ativo"
    assert got[0].finalizados == 4


def test_exclui_usuario_desabilitado():
    from core.reports.analistas_disponiveis import filtrar_analistas_disponiveis, usuario_desabilitado

    assert usuario_desabilitado({"usuario_desabilitado_user": 1})
    assert usuario_desabilitado({"usuario_desabilitado_user": "1"})
    assert not usuario_desabilitado({"usuario_desabilitado_user": 0})
    assert not usuario_desabilitado({})
    users = [
        {
            "nome_user": "Ana Livre",
            "email_user": "ana@x.com",
            "departamento_user": "IMPLANTAÇÃO",
            "usuario_desabilitado_user": 0,
        },
        {
            "nome_user": "Ex Colega",
            "email_user": "ex@x.com",
            "departamento_user": "IMPLANTAÇÃO",
            "usuario_desabilitado_user": 1,
        },
    ]
    got = filtrar_analistas_disponiveis(users, {}, [], dept_principal="IMPLANTAÇÃO")
    assert [a.nome for a in got] == ["Ana Livre"]


def test_exclui_usuario_admin():
    from core.reports.analistas_disponiveis import filtrar_analistas_disponiveis, usuario_admin

    assert usuario_admin({"admin_user": 1})
    assert usuario_admin({"admin_user": "1"})
    assert not usuario_admin({"admin_user": 0})
    users = [
        {
            "nome_user": "Ana Livre",
            "email_user": "ana@x.com",
            "departamento_user": "IMPLANTAÇÃO",
            "usuario_desabilitado_user": 0,
            "admin_user": 0,
        },
        {
            "nome_user": "Chefe Admin",
            "email_user": "admin@x.com",
            "departamento_user": "IMPLANTAÇÃO",
            "usuario_desabilitado_user": 0,
            "admin_user": 1,
        },
    ]
    got = filtrar_analistas_disponiveis(users, {}, [], dept_principal="IMPLANTAÇÃO")
    assert [a.nome for a in got] == ["Ana Livre"]


def test_picos_top3_simultaneos_por_hora():
    from core.reports.picos_hora import PicoHora, intervalos_nos_alvos, top_picos

    dia = TZ_SP.localize(datetime(2026, 9, 14, 0, 0, 0))
    h = lambda hh, mm=0: TZ_SP.localize(datetime(2026, 9, 14, hh, mm, 0))
    intervalos = [
        (h(13, 0), h(14, 30)),
        (h(13, 15), h(15, 0)),
        (h(13, 40), h(14, 10)),
        (h(11, 0), h(12, 0)),
        (h(11, 30), h(12, 30)),
    ]
    top = top_picos(intervalos, dia, top=3)
    assert [p.hora_ini for p in top] == [13, 14, 11]
    assert top[0].max_simultaneos == 3
    assert top[1].max_simultaneos == 3
    assert top[2].max_simultaneos == 2
    assert top[0].label == "13h–14h"
    assert isinstance(top[0], PicoHora)

    eventos = [
        (h(12, 0), "Aguardando Config. Remota"),
        (h(12, 45), "Em Configuração Remota"),
        (h(13, 10), "Aguardando Config. Remota"),
        (h(14, 0), "Em Configuração Remota"),
    ]
    espera = intervalos_nos_alvos(
        eventos,
        alvos=frozenset({"Aguardando Config. Remota"}),
        agora=h(18, 0),
    )
    assert len(espera) == 2
    assert espera[0][1] == h(12, 45)


def test_html_fila_tem_analistas_e_picos_escapados():
    from core.reports.analistas_disponiveis import AnalistaDisponivel
    from core.reports.picos_hora import PicoHora, PicosDia, PicosProjeto

    item = FilaEsperaItem(
        "FUST", 1, "35071225", "<script>", "SP", "SP", None, 3600, "Ana"
    )
    picos = PicosDia(
        fust=PicosProjeto(
            "FUST",
            atendimento=[PicoHora(13, 15)],
            espera=[PicoHora(12, 7)],
        ),
        prodesp=PicosProjeto(
            "PRODESP",
            atendimento=[PicoHora(11, 15)],
            espera=[PicoHora(12, 7)],
        ),
        geral=PicosProjeto(
            "GERAL",
            atendimento=[PicoHora(13, 20)],
            espera=[PicoHora(12, 10)],
        ),
    )
    html = build_fila_email_html(
        gerado_em="14/09/2026 12:00",
        itens=[item],
        minutos_min=30,
        tipo="final",
        analistas=[
            AnalistaDisponivel(
                "Ana <Livre>",
                "ana@x.com",
                status="Indisponível",
                na_plataforma=False,
                finalizados=3,
            )
        ],
        picos=picos,
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Ana &lt;Livre&gt;" in html
    assert "ana@x.com" not in html
    assert "E-mail" not in html
    assert "0 em andamento" not in html
    assert ".env" not in html
    assert "Indisponível" in html
    assert "Inativo" in html
    assert "Finalizado" in html
    assert "13h–14h" in html
    assert "aguardando analista" in html
    assert "GERAL" in html
    assert "Analistas disponíveis" in html


def test_teams_fila_card_nao_inclui_analistas():
    from core.reports.analistas_disponiveis import AnalistaDisponivel
    from core.reports.email_html import build_fila_teams_card

    item = FilaEsperaItem("PRODESP", 2, "2221159", "DPESP", "SAO PAULO", "SP", None, 3600, "")
    card = build_fila_teams_card(
        title="[SUPERVISORES] Fila remota sem analista",
        gerado_em="14/09/2026 22:28",
        itens=[item],
        minutos_min=30,
        tipo="periodico",
        analistas=[
            AnalistaDisponivel(
                "Ana Livre",
                "ana@x.com",
                status="Indisponível",
                na_plataforma=True,
                finalizados=2,
            )
        ],
    )
    blob = str(card)
    kinds = [b.get("type") for b in card["body"]]
    assert kinds.count("ColumnSet") >= 1
    assert "@geral" not in blob
    assert "Ana Livre" not in blob
    assert "2221159" in blob
    assert "Avisos" in blob
    url = "https://example.environment.api.powerplatform.com/powerautomate/fila"
    payload = build_teams_webhook_payload("t", "x", url, card=card, mention_geral=False)
    assert "mentionChannel" not in payload
    assert payload["attachments"][0]["content"]["body"] == card["body"]
    assert payload["body"] != card["body"]
    payload_macro = build_teams_webhook_payload("t", "x", url)
    assert "mentionChannel" not in payload_macro


def test_teams_analistas_card_menciona_geral():
    from core.reports.analistas_disponiveis import AnalistaDisponivel
    from core.reports.email_html import build_analistas_teams_card

    card = build_analistas_teams_card(
        title="[SUPERVISORES] Analistas disponíveis",
        gerado_em="14/09/2026 22:28",
        analistas=[
            AnalistaDisponivel(
                "Ana Livre",
                "ana@x.com",
                status="Indisponível",
                na_plataforma=True,
                finalizados=2,
            )
        ],
    )
    blob = str(card)
    assert "@geral" in blob
    assert "Ana Livre" in blob
    assert "ana@x.com" not in blob
    assert "0 em andamento" not in blob
    assert "Indisponível" in blob
    assert "Ativo" in blob
    assert "Finalizado" in blob
    url = "https://example.environment.api.powerplatform.com/powerautomate/fila"
    payload = build_teams_webhook_payload("t", "x", url, card=card, mention_geral=True)
    assert payload.get("mentionChannel") is True
    assert payload.get("mentionText") == "@geral"
    assert payload["attachments"][0]["content"]["body"] == card["body"]
    assert payload["body"] != card["body"]


def test_teams_analistas_pagina_completa_sem_recorte(monkeypatch):
    from core.reports.analistas_disponiveis import AnalistaDisponivel
    from core.reports.email_html import build_analistas_teams_card, fatiar_analistas_teams

    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_MAX_ANALISTAS", "5")
    muitos = [
        AnalistaDisponivel(f"Analista {i:02d}", status="Indisponível", na_plataforma=False)
        for i in range(20)
    ]
    muitos.append(
        AnalistaDisponivel("Zara Ativa", status="Disponível", na_plataforma=True, finalizados=1)
    )
    fatias = fatiar_analistas_teams(muitos)
    assert len(fatias) == 5
    assert fatias[0][0].nome == "Zara Ativa"
    nomes = [a.nome for fatia in fatias for a in fatia]
    assert "Zara Ativa" in nomes
    assert "Analista 19" in nomes
    assert len(nomes) == 21
    card1 = build_analistas_teams_card(
        title="t",
        gerado_em="14/09/2026 23:00",
        analistas=fatias[0],
        total=21,
        pagina=1,
        paginas=5,
    )
    blob1 = str(card1)
    assert "Zara Ativa" in blob1
    assert "@geral" in blob1
    assert "1/5" in blob1
    assert "no e-mail" not in blob1
    card_fim = build_analistas_teams_card(
        title="t",
        gerado_em="14/09/2026 23:00",
        analistas=fatias[-1],
        total=21,
        pagina=5,
        paginas=5,
    )
    blob_fim = str(card_fim)
    assert "Analista 19" in blob_fim
    assert "@geral" not in blob_fim
    assert "5/5" in blob_fim
    assert "no e-mail" not in blob_fim


def test_enviar_fila_teams_dois_posts(monkeypatch, tmp_path):
    from core.reports.analistas_disponiveis import AnalistaDisponivel
    from core.reports.send_reports import enviar_fila

    item = FilaEsperaItem("PRODESP", 2, "2221159", "DPESP", "SAO PAULO", "SP", None, 3600, "")
    calls: list[dict] = []
    monkeypatch.setenv("SUPERVISORES_FILA_EMAIL_ENABLED", "0")
    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_ENABLED", "1")
    monkeypatch.setenv("SUPERVISORES_FILA_AVISOS_PATH", str(tmp_path / "avisos.json"))
    monkeypatch.delenv("SUPERVISORES_FILA_TEAMS_WEBHOOK_CHAT_URL", raising=False)
    monkeypatch.setenv(
        "SUPERVISORES_FILA_TEAMS_WEBHOOK_URL",
        "https://example.environment.api.powerplatform.com/powerautomate/fila",
    )
    monkeypatch.setattr(
        "core.reports.send_reports.carregar_analistas_disponiveis",
        lambda: [
            AnalistaDisponivel("Ana Livre", status="Disponível", na_plataforma=True, finalizados=1)
        ],
    )
    monkeypatch.setattr("core.reports.send_reports.teams_fila_channel_email", lambda: "")

    def _fake_send(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr("core.reports.send_reports.send_teams_webhook", _fake_send)
    assert enviar_fila(tipo="periodico", itens=[item]).enviado is True
    assert len(calls) == 2
    assert calls[0]["mention_geral"] is False
    assert calls[1]["mention_geral"] is True
    assert "Fila remota" in calls[0]["title"]
    assert "Analistas disponíveis" in calls[1]["title"]
    assert "Ana Livre" not in str(calls[0]["card"])
    assert "Ana Livre" in str(calls[1]["card"])
    assert "2221159" in str(calls[0]["card"])
    assert "1ª vez" in str(calls[0]["card"])
    assert item.avisos == 1


def test_enviar_fila_teams_analistas_em_varias_paginas(monkeypatch, tmp_path):
    from core.reports.analistas_disponiveis import AnalistaDisponivel
    from core.reports.send_reports import enviar_fila

    item = FilaEsperaItem("FUST", 1, "1", "A", "SP", "SP", None, 3600, "")
    calls: list[dict] = []
    monkeypatch.setenv("SUPERVISORES_FILA_EMAIL_ENABLED", "0")
    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_ENABLED", "1")
    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_MAX_ANALISTAS", "5")
    monkeypatch.setenv("SUPERVISORES_FILA_AVISOS_PATH", str(tmp_path / "avisos.json"))
    monkeypatch.delenv("SUPERVISORES_FILA_TEAMS_WEBHOOK_CHAT_URL", raising=False)
    monkeypatch.setenv(
        "SUPERVISORES_FILA_TEAMS_WEBHOOK_URL",
        "https://example.environment.api.powerplatform.com/powerautomate/fila",
    )
    lista = [
        AnalistaDisponivel(f"Analista {i:02d}", status="Indisponível", na_plataforma=False)
        for i in range(12)
    ]
    monkeypatch.setattr("core.reports.send_reports.carregar_analistas_disponiveis", lambda: lista)
    monkeypatch.setattr("core.reports.send_reports.teams_fila_channel_email", lambda: "")

    def _fake_send(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr("core.reports.send_reports.send_teams_webhook", _fake_send)
    assert enviar_fila(tipo="periodico", itens=[item]).enviado is True
    assert len(calls) == 4  # 1 fila + 3 páginas de analistas
    assert calls[0]["mention_geral"] is False
    assert calls[1]["mention_geral"] is True
    assert calls[2]["mention_geral"] is False
    assert calls[3]["mention_geral"] is False
    blob = " ".join(str(c["card"]) for c in calls[1:])
    assert "Analista 00" in blob
    assert "Analista 11" in blob
    assert "no e-mail" not in blob
    assert "1ª vez" in str(calls[0]["card"])


def test_enviar_fila_teams_replica_no_chat(monkeypatch, tmp_path):
    from core.reports.analistas_disponiveis import AnalistaDisponivel
    from core.reports.send_reports import enviar_fila

    item = FilaEsperaItem("PRODESP", 2, "9", "U", "SP", "SP", None, 3600, "")
    item.avisos = 3
    urls: list[str] = []
    monkeypatch.setenv("SUPERVISORES_FILA_EMAIL_ENABLED", "0")
    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_ENABLED", "1")
    monkeypatch.setenv("SUPERVISORES_FILA_AVISOS_PATH", str(tmp_path / "avisos.json"))
    monkeypatch.setenv(
        "SUPERVISORES_FILA_TEAMS_WEBHOOK_URL",
        "https://example.environment.api.powerplatform.com/powerautomate/fila",
    )
    monkeypatch.setenv(
        "SUPERVISORES_FILA_TEAMS_WEBHOOK_CHAT_URL",
        "https://example.environment.api.powerautomate.com/powerautomate/chat",
    )
    monkeypatch.setattr(
        "core.reports.send_reports.carregar_analistas_disponiveis",
        lambda: [AnalistaDisponivel("Ana Livre")],
    )
    monkeypatch.setattr("core.reports.send_reports.teams_fila_channel_email", lambda: "")

    def _fake_send(**kwargs):
        urls.append(kwargs.get("webhook_url") or "")
        return True

    monkeypatch.setattr("core.reports.send_reports.send_teams_webhook", _fake_send)
    assert enviar_fila(tipo="periodico", itens=[item]).enviado is True
    assert urls.count("https://example.environment.api.powerplatform.com/powerautomate/fila") == 2
    assert urls.count("https://example.environment.api.powerautomate.com/powerautomate/chat") == 2
    assert item.avisos == 3


def test_webhooks_macro_e_fila_sao_independentes(monkeypatch):
    monkeypatch.setenv("SUPERVISORES_MACRO_TEAMS_WEBHOOK_URL", "https://macro.example/hook")
    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_WEBHOOK_URL", "https://fila.example/hook")
    monkeypatch.setenv("SUPERVISORES_FILA_TEAMS_WEBHOOK_CHAT_URL", "https://chat.example/hook")
    from core.reports.env_config import teams_fila_webhook_url, teams_fila_webhook_urls, teams_webhook_url

    assert teams_webhook_url() == "https://macro.example/hook"
    assert teams_fila_webhook_url() == "https://fila.example/hook"
    assert teams_fila_webhook_urls() == [
        "https://fila.example/hook",
        "https://chat.example/hook",
    ]
