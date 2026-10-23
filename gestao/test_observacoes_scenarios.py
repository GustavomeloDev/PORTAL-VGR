"""Testes de integração — observações PRODESP (insert/delete/reload/vínculo).

Rodar na raiz do projeto (venv ``.venv_portal_pessoal``):

  .venv_portal_pessoal\\Scripts\\python.exe -m prodesp.prodesp.gestao.test_observacoes_scenarios

Estrutura do pacote: ``prodesp/prodesp/README.md``.

Valida as 4 regras no banco (sem UI):
  1. Persistência imediata (unidade + atendimento)
  2. Listagem após persistir
  3. Vínculo ao criar atendimento
  4. GET mesclado (atendimento + unidade NULL)
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime

from prodesp.app import (
    get_db_connection,
    _prodesp_listar_observacoes_atendimento_e_unidade,
    _prodesp_listar_observacoes_unidade_agendado,
    _prodesp_vincular_observacoes_unidade_ao_atendimento,
)

FAILURES: list[str] = []
OK: list[str] = []

MARKER = uuid.uuid4().hex[:8].upper()  # cabe em id_vgr_unidades (max 15)
TS = datetime.now().strftime("%d/%m/%Y %H:%M:%S")


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        OK.append(name)
    else:
        msg = f"{name}"
        if detail:
            msg += f": {detail}"
        FAILURES.append(msg)


def check_eq(name: str, got, expected, field=""):
    if got == expected:
        OK.append(name)
    else:
        FAILURES.append(f"{name}: esperado {expected!r}, got {got!r} {field}")


def _insert_unidade_obs(cursor, id_unidade: int, texto: str) -> int:
    cursor.execute(
        """INSERT INTO observacoes
           (id_unidades_observacoes, observacoes, timestamp_observacoes, id_atendimentos_observacoes)
           VALUES (%s, %s, %s, NULL)""",
        (id_unidade, texto, datetime.now()),
    )
    return cursor.lastrowid


def _insert_atendimento_obs(cursor, id_unidade: int, id_atendimento: int, texto: str) -> int:
    cursor.execute(
        """INSERT INTO observacoes
           (id_unidades_observacoes, observacoes, timestamp_observacoes, id_atendimentos_observacoes)
           VALUES (%s, %s, %s, %s)""",
        (id_unidade, texto, datetime.now(), id_atendimento),
    )
    return cursor.lastrowid


def _delete_obs_by_ids(cursor, ids: list[int]):
    if not ids:
        return
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(f"DELETE FROM observacoes WHERE id_observacoes IN ({placeholders})", ids)


def run():
    from run import app
    from flask import session

    with app.app_context():
        with app.test_request_context():
            session["re_usuario"] = "TEST_OBS"
            session["nome_usuario"] = "Teste Observações"
            _run_scenarios()


def _run_scenarios():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    id_unidade = None
    id_atendimento = None
    created_obs_ids: list[int] = []

    try:
        # --- Setup: unidade de teste ---
        id_vgr = f"T{MARKER}"  # max 15 chars
        cursor.execute(
            """INSERT INTO unidades (id_vgr_unidades, nome_unidades, endereco_unidades,
               numero_unidades, bairro_unidades, municipio_unidades, estado_unidades)
               VALUES (%s, %s, '', '', '', 'Teste', 'SP')""",
            (id_vgr, f"Unidade {MARKER}"),
        )
        id_unidade = cursor.lastrowid
        conn.commit()
        check("setup: unidade criada", id_unidade is not None, f"id={id_unidade}")

        # --- Cenário 1: insert unidade (pré-atendimento) ---
        txt_unidade_1 = f"OBS{MARKER}_U1"
        txt_unidade_2 = f"OBS{MARKER}_U2"
        oid_u1 = _insert_unidade_obs(cursor, id_unidade, txt_unidade_1)
        oid_u2 = _insert_unidade_obs(cursor, id_unidade, txt_unidade_2)
        created_obs_ids.extend([oid_u1, oid_u2])
        conn.commit()

        lista_unidade = _prodesp_listar_observacoes_unidade_agendado(cursor, id_unidade)
        textos_unidade = {o["texto"] for o in lista_unidade}
        check(
            "regra1/unidade: insert persiste no banco",
            txt_unidade_1 in textos_unidade and txt_unidade_2 in textos_unidade,
            f"textos={textos_unidade}",
        )
        check_eq(
            "regra1/unidade: quantidade após insert",
            len([o for o in lista_unidade if MARKER in o["texto"]]),
            2,
        )

        # --- Cenário 2: delete unidade (simula unidades-observacoes-update delete) ---
        cursor.execute(
            """DELETE FROM observacoes
               WHERE id_observacoes = %s AND id_unidades_observacoes = %s
                 AND id_atendimentos_observacoes IS NULL""",
            (oid_u2, id_unidade),
        )
        conn.commit()
        created_obs_ids.remove(oid_u2)

        lista_pos_delete = _prodesp_listar_observacoes_unidade_agendado(cursor, id_unidade)
        textos_pos = {o["texto"] for o in lista_pos_delete}
        check(
            "regra1/unidade: delete remove do banco",
            txt_unidade_1 in textos_pos and txt_unidade_2 not in textos_pos,
            f"textos={textos_pos}",
        )

        # --- Setup atendimento ---
        cursor.execute(
            """INSERT INTO atendimentos
               (status_atendimentos, substatus_atendimentos,
                analista_atuante_atendimentos, analista_configuracao_atendimentos,
                analista_mpls_atendimentos, analista_caderno_teste_atendimentos,
                contratada_atendimentos, field_atendimentos, contato_field_atendimentos,
                logs_atendimentos, id_unidades_atendimentos, data_atendimentos,
                horario_inicio_atendimentos)
               VALUES ('Em Atendimento', 'Triagem', 'Teste Auto', '', '', '', '', '', '', '', %s, %s, %s)""",
            (id_unidade, datetime.now(), datetime.now().strftime("%H:%M:%S")),
        )
        id_atendimento = cursor.lastrowid
        conn.commit()
        check("setup: atendimento criado", id_atendimento is not None, f"id={id_atendimento}")

        # --- Cenário 3: vínculo ao iniciar atendimento (regra 3) ---
        n_vinculadas = _prodesp_vincular_observacoes_unidade_ao_atendimento(
            cursor, conn, id_unidade, id_atendimento
        )
        conn.commit()
        check_eq("regra3: obs unidade vinculadas ao create", n_vinculadas, 1)

        cursor.execute(
            """SELECT COUNT(*) AS c FROM observacoes
               WHERE id_unidades_observacoes = %s AND id_atendimentos_observacoes IS NULL""",
            (id_unidade,),
        )
        check_eq(
            "regra3: nenhuma obs unidade órfã após vínculo",
            cursor.fetchone()["c"],
            0,
        )

        cursor.execute(
            """SELECT id_atendimentos_observacoes FROM observacoes WHERE id_observacoes = %s""",
            (oid_u1,),
        )
        row_vinc = cursor.fetchone()
        check_eq(
            "regra3: obs antiga aponta para atendimento",
            row_vinc["id_atendimentos_observacoes"],
            id_atendimento,
        )

        # --- Cenário 4: insert atendimento direto (regra 1 edit/create) ---
        txt_at_1 = f"OBS{MARKER}_A1"
        txt_at_2 = f"OBS{MARKER}_A2"
        oid_a1 = _insert_atendimento_obs(cursor, id_unidade, id_atendimento, txt_at_1)
        oid_a2 = _insert_atendimento_obs(cursor, id_unidade, id_atendimento, txt_at_2)
        created_obs_ids.extend([oid_a1, oid_a2])
        conn.commit()

        # --- Cenário 5: GET mesclado (regra 4) ---
        mesclado = _prodesp_listar_observacoes_atendimento_e_unidade(
            cursor, id_atendimento, id_unidade
        )
        textos_mesclado = {o["texto"] for o in mesclado}
        check(
            "regra4: GET mesclado inclui obs vinculadas",
            txt_unidade_1 in textos_mesclado
            and txt_at_1 in textos_mesclado
            and txt_at_2 in textos_mesclado,
            f"textos={textos_mesclado}",
        )
        check_eq(
            "regra4: total observações no mesclado",
            len([o for o in mesclado if MARKER in o["texto"]]),
            3,
        )

        # Obs unidade NULL extra (ainda não vinculada) deve aparecer no mesclado
        txt_orfa = f"OBS{MARKER}_ORF"
        oid_orfa = _insert_unidade_obs(cursor, id_unidade, txt_orfa)
        created_obs_ids.append(oid_orfa)
        conn.commit()

        mesclado2 = _prodesp_listar_observacoes_atendimento_e_unidade(
            cursor, id_atendimento, id_unidade
        )
        textos_m2 = {o["texto"] for o in mesclado2}
        check(
            "regra4: GET mesclado inclui obs unidade NULL",
            txt_orfa in textos_m2,
            f"textos={textos_m2}",
        )

        # --- Cenário 6: delete atendimento (regra 1 delete edit) ---
        cursor.execute("DELETE FROM observacoes WHERE id_observacoes = %s", (oid_a2,))
        conn.commit()
        created_obs_ids.remove(oid_a2)

        mesclado_pos_del = _prodesp_listar_observacoes_atendimento_e_unidade(
            cursor, id_atendimento, id_unidade
        )
        textos_del = {o["texto"] for o in mesclado_pos_del}
        check(
            "regra1/atendimento: delete persiste no banco",
            txt_at_2 not in textos_del and txt_at_1 in textos_del,
            f"textos={textos_del}",
        )

        # --- Cenário 7: deduplicação no create (texto já existente) ---
        cursor.execute(
            """
            SELECT 1 FROM observacoes
            WHERE id_atendimentos_observacoes = %s AND observacoes = %s
            LIMIT 1
            """,
            (id_atendimento, txt_at_1),
        )
        check(
            "regra4/create: detecta duplicata por texto",
            cursor.fetchone() is not None,
        )

        # --- Cenário 8: reload após persistir (regra 2 — listagem = fonte única) ---
        cursor.execute(
            """SELECT id_observacoes AS id, observacoes AS texto
               FROM observacoes WHERE id_atendimentos_observacoes = %s""",
            (id_atendimento,),
        )
        db_rows = cursor.fetchall()
        db_textos = {r["texto"] for r in db_rows}
        reload_textos = {o["texto"] for o in mesclado_pos_del if o.get("id_atendimentos_observacoes")}
        check(
            "regra2: reload reflete banco (obs do atendimento)",
            txt_at_1 in db_textos and txt_at_1 in reload_textos,
        )

    except Exception as exc:
        FAILURES.append(f"exceção não tratada: {exc}")
        raise
    finally:
        # Cleanup
        try:
            if id_atendimento:
                cursor.execute(
                    "DELETE FROM atendimentos_status_log WHERE id_atendimentos_log = %s",
                    (id_atendimento,),
                )
                cursor.execute(
                    "DELETE FROM historico WHERE id_registro_afetado_historico = %s AND tabela_afetada_historico = 'atendimentos'",
                    (id_atendimento,),
                )
                cursor.execute(
                    "DELETE FROM observacoes WHERE id_atendimentos_observacoes = %s",
                    (id_atendimento,),
                )
                cursor.execute(
                    "DELETE FROM atendimentos WHERE id_atendimentos = %s",
                    (id_atendimento,),
                )
            if id_unidade:
                cursor.execute(
                    "DELETE FROM historico WHERE id_registro_afetado_historico = %s AND tabela_afetada_historico = 'unidades'",
                    (id_unidade,),
                )
                cursor.execute(
                    "DELETE FROM observacoes WHERE id_unidades_observacoes = %s",
                    (id_unidade,),
                )
                cursor.execute("DELETE FROM unidades WHERE id_unidades = %s", (id_unidade,))
            conn.commit()
        except Exception as cleanup_exc:
            FAILURES.append(f"cleanup falhou: {cleanup_exc}")
        finally:
            cursor.close()
            conn.close()


def main():
    print(f"=== Testes observações PRODESP [{MARKER}] ===\n")
    run()
    print(f"OK ({len(OK)}):")
    for name in OK:
        print(f"  [OK] {name}")
    if FAILURES:
        print(f"\nFALHAS ({len(FAILURES)}):")
        for name in FAILURES:
            print(f"  [FAIL] {name}")
        print(f"\nResultado: {len(FAILURES)} falha(s)")
        sys.exit(1)
    print(f"\nResultado: todos os {len(OK)} cenários passaram.")
    sys.exit(0)


if __name__ == "__main__":
    main()
