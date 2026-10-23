#!/usr/bin/env python
"""Smoke CLI: CRUD catálogo secretaria + geração CSV (MySQL PRODESP).

Requer migration ``prodesp/sql/021_blueprint_secretaria_catalog.sql`` aplicada
e credenciais PRODESP no ``.env``.

Uso (raiz do repo, venv portal pessoal):

    .venv_portal_pessoal\\Scripts\\python.exe ^
      prodesp/prodesp/blueprint/smoke_blueprint_secretaria_catalog.py

Exit 0 = OK; exit 1 = falha; exit 2 = skip (sem DB/tabela).
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
import uuid

# Raiz do monorepo no path
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _log(msg: str) -> None:
    print(f"[smoke-bp-sec] {msg}")


def main() -> int:
    from prodesp.prodesp.blueprint.blueprint_catalog import (
        StaticCatalog,
        clear_test_catalog,
        invalidate_catalog_cache,
        resolve_rule,
        set_db_catalog_loader,
    )
    from prodesp.prodesp.blueprint.blueprint_secretaria_repo import (
        create_secretaria,
        delete_hard,
        load_all_rules,
        soft_deactivate,
        table_exists,
        update_secretaria,
    )
    from prodesp.prodesp.blueprint.prodesp_csv_generator import (
        gerar_csv_blueprint_prodesp,
    )

    clear_test_catalog()
    invalidate_catalog_cache()

    try:
        from prodesp.credentials.db_connection import get_prodesp_db_connection

        conn = get_prodesp_db_connection(use_pool=False)
    except Exception as e:
        _log(f"SKIP: nao conectou no MySQL PRODESP ({e})")
        return 2

    cur = conn.cursor(dictionary=True)
    if not table_exists(cur):
        _log("SKIP: tabela prodesp_blueprint_secretaria ausente — rode sql/021_blueprint_secretaria_catalog.sql")
        cur.close()
        conn.close()
        return 2

    def loader():
        c = get_prodesp_db_connection(use_pool=False)
        k = c.cursor(dictionary=True)
        try:
            return StaticCatalog(load_all_rules(k))
        finally:
            k.close()
            c.close()

    set_db_catalog_loader(loader)
    invalidate_catalog_cache()

    suf = uuid.uuid4().hex[:8].upper()
    acr = f"ZTST{suf}"[:40]
    alias = f"ZTSA{suf[:7]}"[:40]
    tpl_a = f"{acr}_HUB-C3-C4_40F_REDE_LAN_1"
    tpl_b = f"{acr}_EDIT_HUB-C3-C4_40F_REDE_LAN_1"
    sec_id = None

    unidade = {
        "acronimo_unidades": acr,
        "hostname_unidades": f"smoke-{suf.lower()}",
        "ip_lan_01_unidades": "10.20.30.40/24",
        "loopback_cliente_unidades": "10.252.1.1",
        "loopback_on_bgp_unidades": "10.253.1.1",
        "loopback_vivo_unidades": "10.254.1.1",
    }
    equipamento = {
        "serial_equipamentos": "FGT40FTKSMOKE01",
        "modelo_equipamentos": "FortiGate 40F",
    }
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

    def gerar():
        with tempfile.TemporaryDirectory() as tmp:
            from prodesp.prodesp.blueprint import prodesp_csv_generator as gen

            old = gen.CSV_DIR
            try:
                gen.CSV_DIR = tmp
                path = gerar_csv_blueprint_prodesp(unidade, equipamento, links)
                with open(path, encoding="utf-8-sig", newline="") as f:
                    rdr = csv.reader(f, delimiter=";")
                    h = next(rdr)
                    v = next(rdr)
                return dict(zip(h, v))
            finally:
                gen.CSV_DIR = old

    try:
        _log(f"1) CREATE {acr} template={tpl_a}")
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
            updated_by="smoke-cli",
            conn=conn,
        )
        if msg:
            raise RuntimeError(f"create: {msg}")
        sec_id = new_id
        conn.commit()
        invalidate_catalog_cache()

        r = resolve_rule(acr)
        if not r or r.device_blueprint_template != tpl_a:
            raise RuntimeError(f"resolve apos create falhou: {r}")
        if not resolve_rule(alias):
            raise RuntimeError("alias nao resolve apos create")
        row = gerar()
        if row.get("Device Blueprint") != tpl_a:
            raise RuntimeError(f"CSV create device={row.get('Device Blueprint')!r}")
        if "MV_REDE_LAN" not in row:
            raise RuntimeError("CSV create sem MV_REDE_LAN")
        _log(f"   OK create -> Device={tpl_a} MV_REDE_LAN={row.get('MV_REDE_LAN')}")

        _log(f"2) UPDATE template -> {tpl_b}")
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
            updated_by="smoke-cli",
            conn=conn,
        )
        if not ok:
            raise RuntimeError(f"update: {msg}")
        conn.commit()
        invalidate_catalog_cache()
        row2 = gerar()
        if row2.get("Device Blueprint") != tpl_b:
            raise RuntimeError(f"CSV edit device={row2.get('Device Blueprint')!r}")
        _log(f"   OK edit -> Device={tpl_b}")

        _log("3) SOFT deactivate -> fallback BP_OES + REDE_LAN")
        ok, msg = soft_deactivate(cur, sec_id, updated_by="smoke-cli", conn=conn)
        if not ok:
            raise RuntimeError(f"soft: {msg}")
        conn.commit()
        invalidate_catalog_cache()
        if resolve_rule(acr) is not None:
            raise RuntimeError("ainda resolve apos inativar")
        row3 = gerar()
        if row3.get("Device Blueprint") != "BP_OES_40F":
            raise RuntimeError(f"fallback device={row3.get('Device Blueprint')!r}")
        if "MV_REDE_LAN" not in row3 or "MV_10_" in row3:
            raise RuntimeError("fallback deveria ser layout REDE_LAN")
        _log(f"   OK inativo -> Device=BP_OES_40F MV_REDE_LAN={row3.get('MV_REDE_LAN')}")

        _log("SMOKE OK")
        return 0
    except Exception as e:
        _log(f"FALHA: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 1
    finally:
        if sec_id is not None:
            try:
                delete_hard(cur, sec_id, conn=conn)
                conn.commit()
                _log(f"cleanup hard-delete id={sec_id}")
            except Exception as e:
                _log(f"cleanup falhou: {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
        try:
            cur.close()
            conn.close()
        except Exception:
            pass
        set_db_catalog_loader(None)
        clear_test_catalog()
        invalidate_catalog_cache()


if __name__ == "__main__":
    raise SystemExit(main())
