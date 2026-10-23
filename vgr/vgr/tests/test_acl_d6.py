"""Testes unitários — ACL D6 / P5 do módulo VGR."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from vgr.vgr.acl import (
    flags_acl,
    pode,
    pode_admin_modulo,
    pode_agendar,
    pode_atendimento,
    pode_blueprint,
    pode_mutar_cadastros,
    pode_supervisao_completa,
)


def _user(*, admin: int = 0, depts: set[str] | None = None, auth: bool = True):
    depts = depts or set()
    primary = next(iter(depts), "")

    def departamentos_todos():
        return frozenset(depts)

    return SimpleNamespace(
        is_authenticated=auth,
        admin_user=admin,
        departamento_user=primary,
        departamentos_todos=departamentos_todos,
    )


class TestAclD6(unittest.TestCase):
    def test_implantacao_cadastros_e_atendimento(self):
        u = _user(depts={"IMPLANTAÇÃO"})
        self.assertTrue(pode_mutar_cadastros(u))
        self.assertTrue(pode_atendimento(u))
        self.assertFalse(pode_agendar(u))
        self.assertTrue(pode_blueprint(u))
        self.assertFalse(pode_supervisao_completa(u))
        self.assertFalse(pode_admin_modulo(u))

    def test_agendamento_pode_agendar_sem_blueprint(self):
        u = _user(depts={"AGENDAMENTO"})
        self.assertTrue(pode_agendar(u))
        self.assertTrue(pode_supervisao_completa(u))
        self.assertFalse(pode_blueprint(u))

    def test_gp_supervisores(self):
        for d in ("GP", "SUPERVISORES"):
            u = _user(depts={d})
            self.assertTrue(pode_agendar(u))
            self.assertTrue(pode_supervisao_completa(u))
            self.assertFalse(pode_blueprint(u))

    def test_admin_p5(self):
        u = _user(admin=1, depts={"IMPLANTAÇÃO"})
        self.assertTrue(pode_agendar(u))
        self.assertTrue(pode_blueprint(u))
        self.assertTrue(pode_supervisao_completa(u))
        self.assertTrue(pode_admin_modulo(u))

    def test_implantacao_mais_agendamento(self):
        u = _user(depts={"IMPLANTAÇÃO", "AGENDAMENTO"})
        self.assertTrue(pode_agendar(u))
        self.assertTrue(pode_blueprint(u))
        self.assertTrue(pode_supervisao_completa(u))

    def test_nao_autenticado(self):
        u = _user(auth=False, depts={"GP"})
        self.assertFalse(pode_mutar_cadastros(u))
        self.assertFalse(pode(u, "agendar"))

    def test_flags(self):
        f = flags_acl(_user(depts={"AGENDAMENTO"}))
        self.assertTrue(f["pode_agendar"])
        self.assertFalse(f["pode_blueprint"])


if __name__ == "__main__":
    unittest.main()
