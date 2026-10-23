"""HTTP smoke: rotas Admin Secretarias Blueprint via Flask test_client.

Nao simula o HTML do browser, mas **simula o usuário autenticado** e chama
as mesmas URLs que o JS (`/prodesp/api/admin/blueprint_secretarias`).

Login:

1. ``PORTAL_SMOKE_RE`` (opcional) — carrega User real por RE no banco login
   (sem senha; so session injected; precisa ser ``admin_user=1``).
2. Senao: usuario admin sintetico com ``login_user`` (sem banco login).

Requer tabela ``prodesp_blueprint_secretaria`` (sql/021) + MySQL PRODESP.

Rodar (raiz do repo):

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest \\
      prodesp/prodesp/blueprint/test_blueprint_secretaria_http.py -q -s

    # com seu RE de teste (admin) — so o id/RE, sem senha no comando:
    $env:PORTAL_SMOKE_RE = "SEU_RE"
    .venv_portal_pessoal\\Scripts\\python.exe -m pytest \\
      prodesp/prodesp/blueprint/test_blueprint_secretaria_http.py -q -s
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
import uuid

import pytest

# Garante path monorepo
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _prodesp_table_ok() -> tuple[bool, str]:
    try:
        from prodesp.credentials.db_connection import get_prodesp_db_connection
        from prodesp.prodesp.blueprint.blueprint_secretaria_repo import table_exists

        conn = get_prodesp_db_connection(use_pool=False)
        cur = conn.cursor(dictionary=True)
        try:
            ok = table_exists(cur)
        finally:
            cur.close()
            conn.close()
        if not ok:
            return False, "tabela prodesp_blueprint_secretaria ausente"
        return True, ""
    except Exception as e:
        return False, f"db prodesp: {e}"


def _load_smoke_user():
    """Prefer RE real (admin); depois 1o admin do login DB; senao sintetico."""
    re_smoke = (os.getenv("PORTAL_SMOKE_RE") or "").strip()
    if re_smoke:
        from login.models import User

        u = User.find_by_re(re_smoke)
        if not u:
            pytest.skip(f"PORTAL_SMOKE_RE={re_smoke!r} nao encontrado no login DB")
        if int(getattr(u, "admin_user", 0) or 0) != 1:
            pytest.skip(f"PORTAL_SMOKE_RE={re_smoke!r} nao e admin_user=1")
        if int(getattr(u, "usuario_desabilitado_user", 0) or 0) == 1:
            pytest.skip(f"PORTAL_SMOKE_RE={re_smoke!r} desabilitado")
        return u, f"real RE={re_smoke} id={u.id}"

    # Auto: primeiro admin ativo no banco login (sem senha — so inject de sessao)
    try:
        from login.credentials.db_connection import get_login_db_connection
        from login.models import User

        conn = get_login_db_connection(use_pool=False)
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT id_user FROM `user` "
                "WHERE admin_user = 1 AND COALESCE(usuario_desabilitado_user, 0) = 0 "
                "ORDER BY id_user ASC LIMIT 1"
            )
            row = cur.fetchone()
        finally:
            cur.close()
            conn.close()
        if row and row.get("id_user") is not None:
            u = User.get(int(row["id_user"]))
            if u:
                return u, f"real admin auto id={u.id_user} re={getattr(u, 're_user', '')}"
    except Exception as e:
        # cai no sintetico
        print(f"[http-smoke] auto-admin: {e}")

    # Admin sintetico compativel com Flask-Login + templates PRODESP
    from flask_login import UserMixin

    class SmokeAdmin(UserMixin):
        id = 900001
        id_user = "900001"
        admin_user = 1
        nome_user = "Smoke Admin BP Sec"
        re_user = "SMOKE_ADMIN"
        email_user = "smoke.admin@test.local"
        usuario_desabilitado_user = 0
        departamento_user = "TI"

        def departamentos_todos(self):
            return frozenset({"TI", "IMPLANTAÇÃO"})

    return SmokeAdmin(), "sintetico admin (sem senha; set PORTAL_SMOKE_RE para fixar seu RE)"


@pytest.fixture(scope="module")
def flask_app():
    ok, reason = _prodesp_table_ok()
    if not ok:
        pytest.skip(reason)

    # Import leve se run.py falhar (secret)
    try:
        from run import app
    except Exception as e:
        pytest.skip(f"nao importou run.app: {e}")

    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    yield app


def _session_as_user(client, user_id: str) -> None:
    """Injeta sessao Flask-Login + flags para nao acionar presence de negocio."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["_id"] = sess.get("_id") or "smoke-session"
        # evita maybe_apply_disponivel → User.get no before_request
        sess["_portal_disponivel_sessao"] = True
        # evita idle logout em smoke
        sess["last_activity"] = __import__("time").time()


@pytest.fixture
def skip_presence_touch(flask_app, monkeypatch):
    """Presence.touch com user sintetico quebraria FK; desliga hook no teste HTTP."""
    monkeypatch.setattr("run.before_request_session_presence", lambda: None)


@pytest.fixture
def authed_client(flask_app, skip_presence_touch):
    """test_client com sessao autenticada (user smoke)."""
    user, how = _load_smoke_user()
    print(f"\n[http-smoke] login mode: {how}")

    # user_loader do app so carrega do DB — injeta loader teste sem senha
    lm = flask_app.login_manager
    prev = getattr(lm, "_user_callback", None)

    def _test_loader(uid):
        if str(uid) == str(user.get_id()):
            return user
        if prev:
            return prev(uid)
        return None

    lm._user_callback = _test_loader

    with flask_app.test_client() as client:
        _session_as_user(client, user.get_id())
        yield client, user

    lm._user_callback = prev


def _gerar_csv_for_acr(acr: str) -> dict:
    from prodesp.prodesp.blueprint.blueprint_catalog import (
        clear_test_catalog,
        invalidate_catalog_cache,
    )
    from prodesp.prodesp.blueprint.prodesp_csv_generator import gerar_csv_blueprint_prodesp

    clear_test_catalog()  # usa loader DB do app
    invalidate_catalog_cache()
    unidade = {
        "acronimo_unidades": acr,
        "hostname_unidades": f"http-smoke-{acr.lower()}",
        "ip_lan_01_unidades": "10.55.66.77/24",
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
    }
    eq = {"serial_equipamentos": "FGT40FTKHTTPSMOKE", "modelo_equipamentos": "FortiGate 40F"}
    links = [
        {
            "tipo_links": "MPLS",
            "ip_wan_links": "10.1.1.1",
            "ip_gateway_links": "10.1.1.2",
            "ip_mascara_links": "255.255.255.252",
            "velocidade_links": "100",
            "id_vgr_links": "1",
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        from prodesp.prodesp.blueprint import prodesp_csv_generator as gen

        old = gen.CSV_DIR
        try:
            gen.CSV_DIR = tmp
            path = gerar_csv_blueprint_prodesp(unidade, eq, links)
            with open(path, encoding="utf-8-sig", newline="") as f:
                r = csv.reader(f, delimiter=";")
                h = next(r)
                v = next(r)
            return dict(zip(h, v))
        finally:
            gen.CSV_DIR = old


def test_http_non_admin_receives_403(flask_app, skip_presence_touch):
    """API admin rejeita nao-admin (gate admin_user)."""
    from flask_login import UserMixin

    class NonAdmin(UserMixin):
        id = 900002
        id_user = 900002
        admin_user = 0
        nome_user = "Nao Admin"
        re_user = "SMOKE_NA"
        usuario_desabilitado_user = 0

    u = NonAdmin()
    lm = flask_app.login_manager
    prev = lm._user_callback

    def _loader(uid):
        if str(uid) == "900002":
            return u
        return prev(uid) if prev else None

    lm._user_callback = _loader
    try:
        with flask_app.test_client() as client:
            _session_as_user(client, "900002")
            r = client.get(
                "/prodesp/api/admin/blueprint_secretarias",
                headers={"Accept": "application/json"},
            )
            assert r.status_code == 403, r.get_data(as_text=True)[:300]
            body = r.get_json() or {}
            assert body.get("success") is False
    finally:
        lm._user_callback = prev


def test_http_admin_crud_and_blueprint_csv(authed_client, flask_app):
    """
    GET page -> POST create -> GET item -> PUT edit -> gerar CSV -> DELETE soft -> fallback CSV.
    """
    client, user = authed_client
    suf = uuid.uuid4().hex[:8].upper()
    acr = f"ZHTT{suf}"[:40]
    alias = f"ZHTA{suf[:6]}"[:40]
    tpl_a = f"{acr}_HUB-C3-C4_40F_REDE_LAN_1"
    tpl_b = f"{acr}_EDIT_HUB-C3-C4_40F_REDE_LAN_1"
    sec_id = None

    try:
        # 1) Pagina admin
        page = client.get("/prodesp/admin/blueprint_secretarias")
        assert page.status_code == 200, page.get_data(as_text=True)[:400]
        assert b"Secretarias Blueprint" in page.data or b"blueprint_secretarias" in page.data or b"tblAdminBpSec" in page.data

        # 2) Listagem
        r_list = client.get(
            "/prodesp/api/admin/blueprint_secretarias",
            headers={"Accept": "application/json"},
        )
        assert r_list.status_code == 200, r_list.get_data(as_text=True)[:400]
        j_list = r_list.get_json()
        assert j_list and j_list.get("success") is not False
        assert "data" in j_list

        # 3) CREATE (payload igual ao JS do modal)
        payload_create = {
            "acronimo": acr,
            "nome_exibicao": acr,
            "device_blueprint_template": tpl_a,
            "layout_csv": "rede_lan",
            "rede_lan_regra": "nova",
            "aliases": alias,
            "ativo": True,
            "aplica_sufixo_lan_dinamico": True,
            "emite_dhcp_server_1": False,
            "legado_omitir_dhcp_server": False,
            "mostrar_em_hint_ui": False,
        }
        r_create = client.post(
            "/prodesp/api/admin/blueprint_secretarias",
            data=json.dumps(payload_create),
            content_type="application/json",
            headers={"Accept": "application/json"},
        )
        assert r_create.status_code == 200, r_create.get_data(as_text=True)[:500]
        j_c = r_create.get_json()
        assert j_c.get("success") is True, j_c
        sec_id = j_c.get("id")
        assert sec_id

        # 4) GET item
        r_get = client.get(
            f"/prodesp/api/admin/blueprint_secretarias/{sec_id}",
            headers={"Accept": "application/json"},
        )
        assert r_get.status_code == 200
        data = (r_get.get_json() or {}).get("data") or {}
        assert data.get("acronimo") == acr
        assert data.get("device_blueprint_template") == tpl_a

        # 5) Gerar blueprint CSV apos create
        row = _gerar_csv_for_acr(acr)
        assert row.get("Device Blueprint") == tpl_a
        assert "MV_REDE_LAN" in row
        assert "MV_10_" not in row

        # 6) PUT edit (troca template) — body igual ao save do modal
        payload_edit = dict(payload_create)
        payload_edit["device_blueprint_template"] = tpl_b
        r_put = client.put(
            f"/prodesp/api/admin/blueprint_secretarias/{sec_id}",
            data=json.dumps(payload_edit),
            content_type="application/json",
            headers={"Accept": "application/json"},
        )
        assert r_put.status_code == 200, r_put.get_data(as_text=True)[:500]
        assert (r_put.get_json() or {}).get("success") is True

        row2 = _gerar_csv_for_acr(acr)
        assert row2.get("Device Blueprint") == tpl_b, row2.get("Device Blueprint")

        # 7) DELETE soft (hard=false) — JSON como no JS
        r_del = client.delete(
            f"/prodesp/api/admin/blueprint_secretarias/{sec_id}",
            data=json.dumps({"hard": False}),
            content_type="application/json",
            headers={"Accept": "application/json"},
        )
        assert r_del.status_code == 200, r_del.get_data(as_text=True)[:500]
        assert (r_del.get_json() or {}).get("success") is True

        row3 = _gerar_csv_for_acr(acr)
        assert row3.get("Device Blueprint") == "BP_OES_40F"
        assert "MV_REDE_LAN" in row3

        print(f"[http-smoke] OK acr={acr} user={getattr(user, 'nome_user', user)}")

    finally:
        if sec_id is not None:
            # limpeza: hard delete se ainda existir
            client.delete(
                f"/prodesp/api/admin/blueprint_secretarias/{sec_id}",
                data=json.dumps({"hard": True}),
                content_type="application/json",
                headers={"Accept": "application/json"},
            )
