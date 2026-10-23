"""Fluxo secretaria catalogo → Device Blueprint → CSV (create / edit / inativo).

Cobre o caminho de negocio sem browser:

1. Criar regra no catalogo (in-memory).
2. Gerar Blueprint e validar Device template.
3. Editar template e gerar de novo.
4. Inativar e confirmar fallback BP_OES + layout REDE_LAN.

Smoke opcional com MySQL (tabela 021):

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest \\
      prodesp/prodesp/blueprint/test_blueprint_secretaria_flow.py -q

    # script CLI independente:
    .venv_portal_pessoal\\Scripts\\python.exe \\
      prodesp/prodesp/blueprint/smoke_blueprint_secretaria_catalog.py
"""
from __future__ import annotations

import csv
import os
import tempfile
import uuid

import pytest

from prodesp.prodesp.blueprint.blueprint_catalog import (
    BUILTIN_SEED_RULES,
    BlueprintSecretariaRule,
    DEFAULT_DEVICE_BLUEPRINT,
    StaticCatalog,
    clear_test_catalog,
    install_test_catalog,
    invalidate_catalog_cache,
    resolve_rule,
    set_db_catalog_loader,
)
from prodesp.prodesp.blueprint.blueprint_secretaria_repo import (
    create_secretaria,
    delete_hard,
    load_all_rules,
    parse_payload,
    soft_deactivate,
    table_exists,
    update_secretaria,
    _audit_map_from_parsed,
    _AUDIT_FIELDS,
)
from prodesp.prodesp.admin_inventory import collect_field_changes

from prodesp.prodesp.blueprint.prodesp_csv_generator import (
    _uses_blueprint_rede_lan_modelo,
    gerar_csv_blueprint_prodesp,
    resolve_device_blueprint_detail,
)

# (imports uuid kept for real_db smoke)


ACR_CREATE = "ZTEST-BP-FLOW"
TPL_A = "ZTEST_HUB-C3-C4_40F_REDE_LAN_1"
TPL_B = "ZTEST_EDIT_HUB-C3-C4_40F_REDE_LAN_1"


def _rule(
    acronimo: str,
    template: str,
    *,
    ativo: bool = True,
    aliases: tuple[str, ...] = (),
) -> BlueprintSecretariaRule:
    return BlueprintSecretariaRule(
        acronimo=acronimo,
        nome_exibicao=acronimo,
        device_blueprint_template=template,
        layout_csv="rede_lan",
        rede_lan_regra="nova",
        aplica_sufixo_lan_dinamico=True,
        ativo=ativo,
        aliases=aliases,
    )


def _unidade(acronimo: str, ip: str = "10.14.128.1/24") -> dict:
    return {
        "acronimo_unidades": acronimo,
        "hostname_unidades": f"host-{acronimo.lower().replace('_', '-')}",
        "ip_lan_01_unidades": ip,
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
    }


def _eq() -> dict:
    return {"serial_equipamentos": "FGT40FTKTESTFLOW", "modelo_equipamentos": "FortiGate 40F"}


def _links() -> list[dict]:
    return [
        {
            "tipo_links": "MPLS",
            "ip_wan_links": "10.1.1.1",
            "ip_gateway_links": "10.1.1.2",
            "ip_mascara_links": "255.255.255.252",
            "velocidade_links": "100",
            "id_vgr_links": "1",
        }
    ]


def _gerar_row(unidade: dict) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as tmp:
        from prodesp.prodesp.blueprint import prodesp_csv_generator as gen

        old = gen.CSV_DIR
        try:
            gen.CSV_DIR = tmp
            path = gerar_csv_blueprint_prodesp(unidade, _eq(), _links())
            with open(path, encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, delimiter=";")
                headers = next(reader)
                values = next(reader)
            return dict(zip(headers, values))
        finally:
            gen.CSV_DIR = old


@pytest.fixture(autouse=True)
def _isolate_catalog():
    clear_test_catalog()
    invalidate_catalog_cache()
    yield
    clear_test_catalog()
    invalidate_catalog_cache()
    set_db_catalog_loader(None)


def test_audit_map_diff_detecta_template_e_aliases():
    """Unitário: diff de auditoria cobre template/aliases (base do historico)."""
    row_a, err = parse_payload(
        {
            "acronimo": "ZAUDIT",
            "device_blueprint_template": "ZAUDIT_TPL_A",
            "layout_csv": "rede_lan",
            "rede_lan_regra": "nova",
            "aliases": "ZAL1",
            "ativo": True,
        },
        is_create=True,
    )
    assert err is None and row_a
    row_b, err = parse_payload(
        {
            "acronimo": "ZAUDIT",
            "device_blueprint_template": "ZAUDIT_TPL_B",
            "layout_csv": "rede_lan",
            "rede_lan_regra": "nova",
            "aliases": "ZAL1,ZAL2",
            "ativo": True,
        },
        is_create=False,
    )
    assert err is None and row_b
    old_m = _audit_map_from_parsed(row_a)
    new_m = _audit_map_from_parsed(row_b)
    changes = collect_field_changes(old_m, new_m)
    campos = {c[0] for c in changes}
    assert "device_blueprint_template" in campos
    assert "aliases" in campos
    assert set(_AUDIT_FIELDS)  # whitelist estável
    for col, ant, novo in changes:
        if col == "device_blueprint_template":
            assert str(ant) == "ZAUDIT_TPL_A"
            assert str(novo) == "ZAUDIT_TPL_B"


def test_create_secretaria_gera_device_blueprint():
    """Simula create no Admin: regra no catalogo → CSV com template novo."""
    rules = list(BUILTIN_SEED_RULES) + [_rule(ACR_CREATE, TPL_A, aliases=("ZTESTBPFLOW",))]
    install_test_catalog(rules)

    r = resolve_rule(ACR_CREATE)
    assert r is not None
    assert r.device_blueprint_template == TPL_A
    assert resolve_rule("ZTESTBPFLOW") is not None

    detail = resolve_device_blueprint_detail(_unidade(ACR_CREATE), _eq())
    assert detail["device_blueprint"] == TPL_A

    row = _gerar_row(_unidade(ACR_CREATE))
    assert row.get("Device Blueprint") == TPL_A
    assert "MV_REDE_LAN" in row
    assert "MV_10_" not in row
    assert row.get("MV_REDE_LAN") == "10.14.128.0"


def test_edit_secretaria_altere_template_e_regenera():
    """Simula edit: troca de Device template e nova geracao de CSV."""
    install_test_catalog(list(BUILTIN_SEED_RULES) + [_rule(ACR_CREATE, TPL_A)])
    row1 = _gerar_row(_unidade(ACR_CREATE))
    assert row1.get("Device Blueprint") == TPL_A

    # Admin salva template novo → reload do catalogo (invalidate + reinstall)
    install_test_catalog(list(BUILTIN_SEED_RULES) + [_rule(ACR_CREATE, TPL_B)])
    invalidate_catalog_cache()

    r = resolve_rule(ACR_CREATE)
    assert r is not None and r.device_blueprint_template == TPL_B

    row2 = _gerar_row(_unidade(ACR_CREATE))
    assert row2.get("Device Blueprint") == TPL_B
    assert row2.get("MV_REDE_LAN") == "10.14.128.0"


def test_inativar_secretaria_fallback_bp_oes_rede_lan():
    """Inativar (ativo=0) → resolve None → BP_OES + layout REDE_LAN."""
    install_test_catalog(
        list(BUILTIN_SEED_RULES)
        + [_rule(ACR_CREATE, TPL_A, ativo=False)]
    )
    assert resolve_rule(ACR_CREATE) is None
    assert _uses_blueprint_rede_lan_modelo(_unidade(ACR_CREATE)) is True

    detail = resolve_device_blueprint_detail(_unidade(ACR_CREATE), _eq())
    assert detail["device_blueprint"] == DEFAULT_DEVICE_BLUEPRINT  # BP_OES_40F

    row = _gerar_row(_unidade(ACR_CREATE))
    assert row.get("Device Blueprint") == "BP_OES_40F"
    assert "MV_REDE_LAN" in row
    assert "MV_10_" not in row
    assert "MV_dhcp_server_1_start" not in row


def test_parse_payload_create_edit_shape():
    """Validadores do payload Admin (create/edit) e par DHCP."""
    row, err = parse_payload(
        {
            "acronimo": ACR_CREATE,
            "device_blueprint_template": TPL_A,
            "layout_csv": "rede_lan",
            "rede_lan_regra": "nova",
            "aliases": "ZTESTBPFLOW",
            "aplica_sufixo_lan_dinamico": True,
        },
        is_create=True,
    )
    assert err is None and row is not None
    assert row["acronimo"] == ACR_CREATE
    assert row["aliases"] == ["ZTESTBPFLOW"]

    row2, err2 = parse_payload(
        {
            "acronimo": ACR_CREATE,
            "device_blueprint_template": TPL_B,
            "layout_csv": "rede_lan",
            "rede_lan_regra": "nova",
            "aliases": "ZTESTBPFLOW",
        },
        is_create=False,
    )
    assert err2 is None and row2 is not None
    assert row2["device_blueprint_template"] == TPL_B


def _try_prodesp_conn():
    try:
        from prodesp.credentials.db_connection import get_prodesp_db_connection

        conn = get_prodesp_db_connection(use_pool=False)
        cur = conn.cursor(dictionary=True)
        if not table_exists(cur):
            cur.close()
            conn.close()
            return None, None, "tabela prodesp_blueprint_secretaria ausente (rode sql/021_...sql)"
        return conn, cur, None
    except Exception as e:
        return None, None, f"db indisponivel: {e}"


def test_real_db_create_edit_generate_cleanup():
    """
    Smoke com MySQL real: CREATE → resolve/CSV → UPDATE template → CSV → soft → hard delete.
    Skip se DB/table nao disponiveis.
    """
    conn, cur, reason = _try_prodesp_conn()
    if conn is None:
        pytest.skip(reason or "db skip")

    # Nao usar catalogo de teste: preferir loader DB
    clear_test_catalog()
    suf = uuid.uuid4().hex[:8].upper()
    acr = f"ZTST{suf}"[:40]
    alias = f"ZTSTA{suf[:6]}"[:40]
    tpl_a = f"{acr}_HUB-C3-C4_40F_REDE_LAN_1"
    tpl_b = f"{acr}_EDIT_HUB-C3-C4_40F_REDE_LAN_1"
    sec_id = None

    def _loader():
        c2 = None
        try:
            from prodesp.credentials.db_connection import get_prodesp_db_connection

            c2 = get_prodesp_db_connection(use_pool=False)
            k = c2.cursor(dictionary=True)
            try:
                return StaticCatalog(load_all_rules(k))
            finally:
                k.close()
        finally:
            if c2 is not None:
                c2.close()

    try:
        set_db_catalog_loader(_loader)
        invalidate_catalog_cache()

        new_id, msg = create_secretaria(
            cur,
            {
                "acronimo": acr,
                "device_blueprint_template": tpl_a,
                "layout_csv": "rede_lan",
                "rede_lan_regra": "nova",
                "aliases": alias,
                "ativo": True,
                "aplica_sufixo_lan_dinamico": True,
            },
            updated_by="smoke-test",
            conn=conn,
        )
        assert msg is None, msg
        assert new_id
        sec_id = new_id
        conn.commit()
        invalidate_catalog_cache()

        cur.execute(
            """
            SELECT COUNT(*) AS n FROM historico
            WHERE tabela_afetada_historico = 'prodesp_blueprint_secretaria'
              AND id_registro_afetado_historico = %s
              AND operacao_historico = 'INSERT'
            """,
            (sec_id,),
        )
        n_ins = int((cur.fetchone() or {}).get("n") or 0)
        assert n_ins >= 1, "create deve gravar linhas em historico"

        r = resolve_rule(acr)
        assert r is not None, "resolve apos create deve achar no DB"
        assert r.device_blueprint_template == tpl_a
        assert resolve_rule(alias) is not None

        row = _gerar_row(_unidade(acr))
        assert row.get("Device Blueprint") == tpl_a
        assert "MV_REDE_LAN" in row

        ok, msg = update_secretaria(
            cur,
            sec_id,
            {
                "acronimo": acr,
                "device_blueprint_template": tpl_b,
                "layout_csv": "rede_lan",
                "rede_lan_regra": "nova",
                "aliases": alias,
                "ativo": True,
                "aplica_sufixo_lan_dinamico": True,
            },
            updated_by="smoke-test",
            conn=conn,
        )
        assert ok and msg is None, msg
        conn.commit()
        invalidate_catalog_cache()

        cur.execute(
            """
            SELECT valor_antigo_historico, valor_novo_historico
            FROM historico
            WHERE tabela_afetada_historico = 'prodesp_blueprint_secretaria'
              AND id_registro_afetado_historico = %s
              AND campo_alterado_historico = 'device_blueprint_template'
              AND operacao_historico = 'UPDATE'
            ORDER BY id_log_historico DESC LIMIT 1
            """,
            (sec_id,),
        )
        h_tpl = cur.fetchone() or {}
        assert str(h_tpl.get("valor_novo_historico") or "") == tpl_b
        assert str(h_tpl.get("valor_antigo_historico") or "") == tpl_a

        r2 = resolve_rule(acr)
        assert r2 is not None and r2.device_blueprint_template == tpl_b
        row2 = _gerar_row(_unidade(acr))
        assert row2.get("Device Blueprint") == tpl_b

        ok, msg = soft_deactivate(cur, sec_id, updated_by="smoke-test", conn=conn)
        assert ok and msg is None, msg
        conn.commit()
        invalidate_catalog_cache()

        cur.execute(
            """
            SELECT valor_novo_historico FROM historico
            WHERE tabela_afetada_historico = 'prodesp_blueprint_secretaria'
              AND id_registro_afetado_historico = %s
              AND campo_alterado_historico = 'ativo'
            ORDER BY id_log_historico DESC LIMIT 1
            """,
            (sec_id,),
        )
        h_ativo = cur.fetchone() or {}
        assert str(h_ativo.get("valor_novo_historico") or "") in ("0", "False", "false")

        assert resolve_rule(acr) is None
        row3 = _gerar_row(_unidade(acr))
        assert row3.get("Device Blueprint") == "BP_OES_40F"
        assert "MV_REDE_LAN" in row3

    finally:
        if sec_id is not None:
            try:
                delete_hard(cur, sec_id, conn=conn)
                conn.commit()
            except Exception:
                conn.rollback()
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        set_db_catalog_loader(None)
        clear_test_catalog()
        invalidate_catalog_cache()
