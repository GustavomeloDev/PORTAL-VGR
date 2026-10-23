"""Testes do CSV de agendamento VGR (validação, relatório e serviço com cursor fake).

Rodar na raiz do repositório:
    python -m unittest vgr.vgr.tests.test_agendamento_csv -v
"""
from __future__ import annotations

import re
import unittest
from datetime import date, timedelta

from vgr.vgr.operacao.agendamento_csv_import_service import (
    processar_importacao_agendamento_csv,
)
from vgr.vgr.operacao.agendamento_csv_notifier import (
    AgendamentoCsvLinha,
    AgendamentoCsvRelatorio,
    build_email_html,
    build_subject,
    linha_export_dict,
    parse_rejeitadas_previa_payload,
)
from vgr.vgr.operacao.agendamento_csv_validacao import (
    motivo_agendamento_csv_corrigivel,
    normalizar_hora_csv,
    normalizar_tipo_servico_csv,
    validar_agendamento_csv_linha,
)

HOJE = date(2026, 10, 13)
AMANHA = (HOJE + timedelta(days=1)).isoformat()
CONTRATADAS = [
    {"id_contratada": 1, "nome_contratada": "DELFIA"},
    {"id_contratada": 2, "nome_contratada": "SPREAD"},
]
NOMES = [c["nome_contratada"] for c in CONTRATADAS]


def _valida(**kw):
    base = dict(
        id_vgr="VGR123",
        tipo_servico="SDWAN",
        data_agendamento=AMANHA,
        hora_agendamento="09:30",
        contratada="delfia",
        field_planejado=None,
        contato_field=None,
        tem_agenda=True,
        contratadas_permitidas=NOMES,
    )
    base.update(kw)
    return validar_agendamento_csv_linha(**base)


class ValidacaoTests(unittest.TestCase):
    def test_linha_ok_normaliza(self):
        err, norm = _valida(tipo_servico="sd-wan")
        self.assertIsNone(err)
        self.assertEqual(norm["tipo_servico"], "SDWAN")
        self.assertEqual(norm["hora_norm"], "09:30:00")
        self.assertEqual(norm["contratada_canonica"], "DELFIA")

    def test_tipo_servico_obrigatorio_e_invalido(self):
        err, _ = _valida(tipo_servico="")
        self.assertIn("Tipo de serviço obrigatório", err)
        err, _ = _valida(tipo_servico="MPLS")
        self.assertIn("Tipo de serviço inválido", err)

    def test_id_vgr_com_espaco(self):
        err, _ = _valida(id_vgr="VGR 1")
        self.assertIn("ID VGR inválido", err)

    def test_agenda_exige_contratada_da_lista(self):
        err, _ = _valida(contratada="")
        self.assertIn("Contratada obrigatória", err)
        err, _ = _valida(contratada="ACME")
        self.assertIn("Contratada inválida", err)

    def test_hora_invalida(self):
        err, _ = _valida(hora_agendamento="A/C")
        self.assertIn("Hora inválida", err)
        self.assertIsNone(normalizar_hora_csv("24:00"))
        self.assertEqual(normalizar_hora_csv("7:05"), "07:05:00")

    def test_field_exige_contato(self):
        err, _ = _valida(field_planejado="João", contato_field="123")
        self.assertIn("Contato Field obrigatório", err)
        err, norm = _valida(field_planejado="João", contato_field="(11) 98888-7777")
        self.assertIsNone(err)
        self.assertEqual(norm["contato_norm"], "11988887777")

    def test_field_contratada_divergente(self):
        err, _ = _valida(field_planejado="SPREAD", contato_field="11988887777")
        self.assertIn("não corresponde à contratada", err)

    def test_corrigivel(self):
        self.assertFalse(motivo_agendamento_csv_corrigivel("Unidade não encontrada (ID VGR...)"))
        self.assertFalse(motivo_agendamento_csv_corrigivel("ID VGR + tipo de serviço duplicado no arquivo"))
        self.assertTrue(motivo_agendamento_csv_corrigivel("Hora inválida (x)."))
        self.assertTrue(
            motivo_agendamento_csv_corrigivel("ID VGR X não possui equipamento SDWIFI (tipos: SDWAN).")
        )
        self.assertEqual(normalizar_tipo_servico_csv(" sdlan ")[0], "SDLAN")


class NotifierTests(unittest.TestCase):
    def test_export_e_email_incluem_tipo_servico(self):
        linha = AgendamentoCsvLinha(
            id_vgr="V1", tipo_servico="SDWIFI", data_agendamento=AMANHA,
            hora_agendamento="09:30:00", contratada="DELFIA", detalhe="Hora inválida",
        )
        d = linha_export_dict(linha)
        self.assertEqual(d["tipo_servico"], "SDWIFI")
        self.assertEqual(d["hora_agendamento"], "09:30")
        self.assertRegex(d["data_agendamento"], r"^\d{2}/\d{2}/\d{4}$")
        self.assertTrue(d["corrigivel"])
        rel = AgendamentoCsvRelatorio(erros=[linha], usuario_upload="<b>x</b>")
        html_body = build_email_html(rel)
        self.assertIn("Serviço", html_body)
        self.assertIn("SDWIFI", html_body)
        self.assertNotIn("<b>x</b>", html_body)  # escapado
        self.assertTrue(build_subject(rel).startswith("[VGR]"))

    def test_rejeitadas_previa(self):
        rows = parse_rejeitadas_previa_payload(
            [{"id_vgr": "A", "tipo_servico": "SDWAN", "motivo": "x" * 900}, {"id_vgr": ""}, "lixo"]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0].detalhe), 500)


# ---------------------------------------------------------------------------
# Cursor fake (roteia por SQL) — sem MySQL
# ---------------------------------------------------------------------------


def _eq(i, uni, vgr, tipo, ativa=1, ha=0):
    return dict(id_equipamento=i, id_unidade=uni, id_vgr=vgr, tipo_servico=tipo, ativo=1,
                id_cliente=1, nome_unidade=f"U{uni}", unidade_ativa=ativa, ha=ha)


class FakeDb:
    def __init__(self):
        self.equipamentos = [
            _eq(1, 10, "VGR10", "SDWAN"), _eq(2, 10, "VGR10", "SDWIFI"),
            _eq(3, 20, "VGR20", "SDWAN"),
            _eq(4, 30, "VGR30", "SDWAN"),
            _eq(5, 40, "VGR40", "SDWAN", ativa=0),
            _eq(6, 50, "VGR50", "SDWAN", ha=1),          # HA com 1 SDWAN
            _eq(7, 60, "VGR60", "SDWAN"),                # tem walk-in ativo
            _eq(8, 70, "VGR70", "SDWAN"),                # agenda Agendado + atend iniciado
            _eq(9, 80, "VGR80", None),                   # equipamento sem tipo de serviço
            _eq(10, 90, "VGR90", None, ha=1),            # HA: 1 SDWAN + 1 sem tipo
            _eq(11, 90, "VGR91", "SDWAN", ha=1),
        ]
        self.concluidos = {30: date(2026, 9, 1)}
        self.agendas = {
            20: dict(id_agendamento=200, id_unidade=20, status_agendamento="Aguardando retorno logística",
                     substatus_agendamento=None, data_agendamento=date(2026, 10, 20),
                     hora_agendamento=timedelta(hours=9), analista_destino="Ana",
                     id_contratada_planejada=1),
            70: dict(id_agendamento=700, id_unidade=70, status_agendamento="Agendado",
                     substatus_agendamento=None, data_agendamento=date(2026, 10, 20),
                     hora_agendamento=timedelta(hours=9), analista_destino=None,
                     id_contratada_planejada=1),
        }
        self.atendimentos = [
            dict(id_atendimento=600, id_unidade=60, id_agendamento=None, status_atendimento="Em Atendimento",
                 substatus_atendimento="Aguarda Cliente", atendimento_iniciado=1, ativo=1),
            dict(id_atendimento=701, id_unidade=70, id_agendamento=700, status_atendimento="Em Atendimento",
                 substatus_atendimento="Em Configuração Remota", atendimento_iniciado=1, ativo=1),
        ]
        self.fields = {}
        self.snaps = {"agendamento_fields": [], "atendimento_fields": []}
        self.ins = {}
        self.updates = []
        self.historico = []
        self.savepoints = []
        self.next_id = 1000

    def add(self, tabela, params):
        self.ins.setdefault(tabela, []).append(params)


class FakeCursor:
    def __init__(self, db: FakeDb, fail_on: str | None = None):
        self.db = db
        self._rows = []
        self.lastrowid = None
        self.fail_on = fail_on

    def _new_id(self):
        self.db.next_id += 1
        self.lastrowid = self.db.next_id

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        if self.fail_on and self.fail_on in s:
            raise RuntimeError("boom")
        if s.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK")):
            self.db.savepoints.append(s)
            return
        db = self.db
        if "FROM equipamentos e" in s:
            keys = {str(p).upper() for p in params}
            self._rows = [dict(r) for r in db.equipamentos if r["id_vgr"].upper() in keys]
        elif "COUNT(*) AS n FROM equipamentos" in s:
            cnt = {}
            for e in db.equipamentos:
                if e["id_unidade"] in params and e["tipo_servico"] == "SDWAN":
                    cnt[e["id_unidade"]] = cnt.get(e["id_unidade"], 0) + 1
            self._rows = [{"id_unidade": u, "n": n} for u, n in cnt.items()]
        elif "AS data_concluido" in s:
            self._rows = [{"id_unidade": u, "data_concluido": d} for u, d in db.concluidos.items() if u in params]
        elif s.startswith("SELECT id_agendamento, id_unidade, status_agendamento"):
            self._rows = [dict(a) for u, a in db.agendas.items() if u in params]
        elif s.startswith("SELECT id_atendimento, id_unidade, id_agendamento"):
            self._rows = [dict(a) for a in db.atendimentos if a["id_unidade"] in params]
        elif "FROM fields" in s:
            self._rows = [dict(f) for f in db.fields.values() if f["nome"] in params]
        elif s.startswith("SELECT") and ("FROM agendamento_fields" in s or "FROM atendimento_fields" in s):
            t = "agendamento_fields" if "FROM agendamento_fields" in s else "atendimento_fields"
            self._rows = [dict(v) for v in db.snaps[t] if v["pai"] == params[0]]
        elif s.startswith("INSERT INTO agendamentos"):
            self._new_id(); db.add("agendamentos", params)
        elif s.startswith("INSERT INTO atendimentos"):
            self._new_id(); db.add("atendimentos", params)
        elif s.startswith("INSERT INTO fields"):
            self._new_id()
            db.fields[params[0]] = {"id_field": self.lastrowid, "nome": params[0], "telefone": params[1]}
        elif s.startswith(("INSERT INTO agendamento_fields", "INSERT INTO atendimento_fields")):
            t = s.split()[2]
            db.snaps[t].append(dict(pk=len(db.snaps[t]) + 1, pai=params[0], id_field=params[1], ordem=params[2],
                                    snap_telefone=params[4], snap_contratada_nome=params[5], id_contratada=params[6]))
        elif s.startswith("UPDATE agendamentos"):
            db.updates.append((s, params))
        elif s.startswith(("INSERT", "UPDATE")):
            parts = s.split()
            db.add(parts[2] if parts[0] == "INSERT" else parts[1], params)
        else:
            raise AssertionError(f"SQL inesperado: {s}")

    def executemany(self, sql, seq):
        self.db.historico.extend(seq)

    def fetchall(self):
        return self._rows


def _row(**kw):
    base = dict(id_vgr="VGR10", tipo_servico="SDWAN", data_agendamento=AMANHA,
                hora_agendamento="09:30", contratada="DELFIA")
    base.update(kw)
    return base


class ServiceTests(unittest.TestCase):
    def _run(self, body, db=None, **kw):
        db = db or FakeDb()
        res = processar_importacao_agendamento_csv(
            FakeCursor(db, **kw), body, HOJE, contratadas=CONTRATADAS, user_re="123", user_nome="Teste"
        )
        return db, res

    def test_cria_agenda_ja_agendado_e_atendimento_nao_iniciado(self):
        db, res = self._run([_row()])
        self.assertEqual((res.agendados_count, res.atendimentos_criados), (1, 1))
        ag = db.ins["agendamentos"][0]
        self.assertEqual(ag[0], 10)
        self.assertEqual(ag[1], "Agendado")
        self.assertEqual(ag[3], "09:30:00")
        self.assertEqual(ag[4], 1)  # DELFIA
        at = db.ins["atendimentos"][0]
        self.assertEqual(at[:4], (10, 1001, "Em Atendimento", "Aguarda Gestão"))
        self.assertIn("atendimento_status_log", db.ins)
        self.assertIn("criada como Agendado", res.sucessos[0].detalhe)

    def test_promove_agenda_aberta_para_agendado(self):
        db, res = self._run([_row(id_vgr="vgr20", data_agendamento="2026-10-20", hora_agendamento="10:00")])
        sql, params = db.updates[0]
        self.assertIn("status_agendamento", sql)
        self.assertIn("Agendado", params)
        self.assertNotIn("data_agendamento =", sql)  # data igual não muda
        at = db.ins["atendimentos"][0]
        self.assertEqual(at[1], 200)
        self.assertEqual(at[4], "Ana")  # analista_destino vira analista_atuante
        self.assertIn("publicada como Agendado", res.sucessos[0].detalhe)

    def test_repetido_quando_ja_agendado_sem_mudanca(self):
        db = FakeDb()
        db.agendas[20]["status_agendamento"] = "Agendado"
        db.atendimentos.append(dict(id_atendimento=201, id_unidade=20, id_agendamento=200,
                                    status_atendimento="Em Atendimento", substatus_atendimento="Aguarda Gestão",
                                    atendimento_iniciado=0, ativo=1))
        db, res = self._run([_row(id_vgr="VGR20", data_agendamento="2026-10-20", hora_agendamento="09:00")], db)
        self.assertEqual(len(res.repetidos), 1)
        self.assertNotIn("atendimentos", db.ins)

    def test_bloqueios_negocio(self):
        body = [
            _row(id_vgr="VGR50"),  # HA sem 2 SDWAN
            _row(id_vgr="VGR60"),  # walk-in ativo
            _row(id_vgr="VGR70", hora_agendamento="15:00"),  # atend. iniciado
        ]
        db, res = self._run(body)
        motivos = " | ".join(e.detalhe for e in res.erros)
        self.assertIn("HA exige 2 equipamentos SDWAN", motivos)
        self.assertIn("atendimento ativo #600", motivos)
        self.assertIn("#701 já iniciado", motivos)
        self.assertFalse(res.sucessos)
        self.assertFalse(db.updates)

    def test_tipo_servico_resolve_equipamento_e_unidade_unica(self):
        _, res = self._run([_row(tipo_servico="SDWAN"), _row(tipo_servico="SDWIFI")])
        self.assertEqual(len(res.sucessos), 1)
        self.assertIn("Unidade já processada", res.erros[0].detalhe)

    def test_tipo_servico_sem_equipamento_e_vgr_inexistente(self):
        _, res = self._run([_row(id_vgr="VGR20", tipo_servico="SDLAN"), _row(id_vgr="NAOEXISTE")])
        motivos = [e.detalhe for e in res.erros]
        self.assertTrue(any("já está cadastrado como SDWAN (CSV informou SDLAN)" in m for m in motivos))
        self.assertTrue(any("Unidade não encontrada" in m for m in motivos))

    def test_equipamento_sem_tipo_recebe_tipo_do_csv_e_agenda(self):
        db, res = self._run([_row(id_vgr="VGR80", tipo_servico="SDWIFI")])
        self.assertEqual(db.ins["equipamentos"][0], ("SDWIFI", 9))
        self.assertEqual(res.agendados_count, 1)
        self.assertIn("tipo de serviço definido como SDWIFI", res.sucessos[0].detalhe)
        self.assertTrue(any(h[2] == "equipamentos" and h[6] == "tipo_servico" for h in db.historico))

    def test_tipo_definido_conta_para_ha(self):
        db, res = self._run([_row(id_vgr="VGR90", tipo_servico="SDWAN")])
        self.assertEqual(res.agendados_count, 1, [e.detalhe for e in res.erros])

    def test_tipo_desfeito_se_linha_falha(self):
        db, res = self._run([_row(id_vgr="VGR80")], fail_on="INSERT INTO atendimentos")
        self.assertTrue(any(x.startswith("ROLLBACK TO SAVEPOINT") for x in db.savepoints))
        self.assertEqual(res.erros[0].detalhe, "Erro ao processar o registro.")

    def test_duplicata_concluido_inativa_data_passada(self):
        body = [
            _row(), _row(),
            _row(id_vgr="VGR30"),
            _row(id_vgr="VGR40"),
            _row(id_vgr="VGR20", data_agendamento="2026-10-01"),
        ]
        _, res = self._run(body)
        motivos = " | ".join(e.detalhe for e in res.erros)
        self.assertIn("duplicado no arquivo", motivos)
        self.assertIn("atendimento concluído (último em 01/09/2026)", motivos)
        self.assertIn("Unidade inativa", motivos)
        self.assertIn("anterior a hoje", motivos)
        self.assertEqual(len(res.sucessos), 1)

    def test_planejamento_sem_data_nao_publica(self):
        db, res = self._run([dict(id_vgr="VGR20", tipo_servico="SDWAN", contratada="SPREAD")])
        sql, params = db.updates[0]
        self.assertNotIn("status_agendamento", sql)
        self.assertNotIn("atendimentos", db.ins)
        self.assertEqual(res.agendados_count, 0)

    def test_field_snapshot_na_agenda_e_no_atendimento(self):
        db, res = self._run([_row(field="João Técnico", contato_field="11988887777")])
        self.assertIn("João Técnico", db.fields)
        self.assertEqual(len(db.snaps["agendamento_fields"]), 1)
        self.assertEqual(len(db.snaps["atendimento_fields"]), 1)
        self.assertEqual(db.snaps["atendimento_fields"][0]["snap_contratada_nome"], "DELFIA")

    def test_erro_na_linha_faz_rollback_do_savepoint(self):
        db, res = self._run([_row()], fail_on="INSERT INTO atendimentos")
        self.assertEqual(res.erros[0].detalhe, "Erro ao processar o registro.")
        self.assertTrue(any(x.startswith("ROLLBACK TO SAVEPOINT") for x in db.savepoints))
        self.assertEqual(res.agendados_count, 0)


if __name__ == "__main__":
    unittest.main()
