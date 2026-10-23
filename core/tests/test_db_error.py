"""Mensagens de erro de banco: claras no analista e em uma linha no log."""

from __future__ import annotations

import unittest

from core.utils.db_error import explain_db_error
from core.utils.fortinet_serial import msg_serial_duplicado_global


class _Exc(Exception):
    def __init__(self, msg: str, errno: int | None = None):
        super().__init__(msg)
        self.errno = errno


def _info(errno: int, msg: str, **kw):
    return explain_db_error(_Exc(msg, errno), contexto="gerar_csv_dma id_unidade=100", **kw)


class TestDbError(unittest.TestCase):
    def test_serial_duplicado_mesma_frase_log_e_usuario(self):
        info = _info(
            1062,
            "1062 (23000): Duplicate entry 'FGT40FTK2409BNJP' "
            "for key 'equipamentos.uq_equipamentos_serial'",
            acao="salvar o blueprint e gerar o CSV",
        )
        esperado = msg_serial_duplicado_global("FGT40FTK2409BNJP")
        self.assertEqual(info.user_message, esperado)
        self.assertTrue(info.log_message.startswith("gerar_csv_dma id_unidade=100: "))
        self.assertIn(esperado, info.log_message)
        self.assertNotIn("\n", info.log_message)
        self.assertNotIn("Traceback", info.log_message)

    def test_duplicado_generico_sem_sql_no_usuario(self):
        info = _info(1062, "1062 (23000): Duplicate entry 'X' for key 'links.uq_algo'")
        self.assertIn("Já existe um cadastro", info.user_message)
        self.assertNotIn("uq_algo", info.user_message)
        self.assertIn("chave=uq_algo", info.log_message)

    def test_primary_duplo_envio(self):
        info = _info(1062, "Duplicate entry '1' for key 'PRIMARY'")
        self.assertIn("duplo clique", info.user_message)

    def test_hostname_unico(self):
        info = _info(
            1062,
            "Duplicate entry 'dma-spk-loja01' for key 'equipamentos.uq_hostname'",
        )
        self.assertIn("hostname", info.user_message.lower())
        self.assertNotIn("dma-spk-loja01", info.user_message)

    def test_campo_longo_com_rotulo(self):
        info = _info(1406, "Data too long for column 'hostname' at row 1")
        self.assertIn("Hostname", info.user_message)
        self.assertNotIn("hostname", info.user_message)

    def test_campo_longo_coluna_desconhecida_nao_vaza(self):
        info = _info(1406, "Data too long for column 'secret_col' at row 1")
        self.assertNotIn("secret_col", info.user_message)
        self.assertIn("secret_col", info.log_message)

    def test_not_null(self):
        info = _info(1048, "Column 'serial' cannot be null")
        self.assertIn("obrigatório", info.user_message.lower())
        self.assertNotIn("serial", info.user_message.lower())

    def test_lat_long_fora_intervalo(self):
        info = _info(1264, "Out of range value for column 'latitude'")
        self.assertIn("Latitude", info.user_message)

    def test_enum_invalido(self):
        info = _info(1265, "Data truncated for column 'modo_conexao' at row 1")
        self.assertIn("lista fechada", info.user_message)
        self.assertNotIn("modo_conexao", info.user_message)

    def test_fk_filho(self):
        info = _info(
            1452,
            "Cannot add or update a child row: a foreign key constraint fails "
            "(`multi`.`links`, CONSTRAINT `fk_links_equipamento`)",
        )
        self.assertIn("referência inválida", info.user_message)
        self.assertNotIn("fk_links", info.user_message)
        self.assertNotIn("multi", info.user_message)

    def test_fk_pai(self):
        info = _info(1451, "Cannot delete or update a parent row")
        self.assertIn("dependem dele", info.user_message)

    def test_deadlock(self):
        info = _info(1213, "Deadlock found when trying to get lock")
        self.assertIn("ocupado", info.user_message)

    def test_lock_wait(self):
        info = _info(1205, "Lock wait timeout exceeded")
        self.assertIn("ocupado", info.user_message)

    def test_charset(self):
        info = _info(1366, "Incorrect string value: '\\xF0\\x9F' for column 'endereco'")
        self.assertIn("caracteres", info.user_message.lower())
        self.assertNotIn("endereco", info.user_message)

    def test_inesperado_uma_linha(self):
        info = _info(
            1234,
            "boom\nSELECT * FROM secret",
            acao="salvar o blueprint e gerar o CSV",
        )
        self.assertIn("Não foi possível salvar o blueprint", info.user_message)
        self.assertNotIn("SELECT", info.user_message)
        self.assertNotIn("\n", info.log_message)
        self.assertIn("boom", info.log_message)

    def test_conexao(self):
        info = explain_db_error(
            _Exc("Can't connect to MySQL server", 2003),
            contexto="persist",
            acao="salvar",
        )
        self.assertIn("Tente novamente", info.user_message)
        self.assertIn("persist:", info.log_message)

    def test_csv_arquivo(self):
        err = FileNotFoundError("No such file")
        err.filename = r"C:\portal\dma\static\csv\x.csv"
        info = explain_db_error(err, contexto="gerar_csv_dma id_unidade=1", acao="gerar")
        self.assertIn("arquivo CSV", info.user_message)
        self.assertNotIn("C:\\portal", info.user_message)

    def test_schema(self):
        info = _info(1054, "Unknown column 'id_vgr' in 'field list'")
        self.assertIn("estrutura do banco", info.user_message)
        self.assertNotIn("id_vgr", info.user_message)


class TestDbErrorSeguranca(unittest.TestCase):
    def test_xss_no_serial_nao_entra_html(self):
        info = _info(
            1062,
            "Duplicate entry '<script>alert(1)</script>' "
            "for key 'equipamentos.uq_equipamentos_serial'",
        )
        self.assertNotIn("<script", info.user_message)
        self.assertNotIn("</script>", info.user_message)

    def test_sql_e_traceback_nunca_no_usuario(self):
        payloads = [
            (1062, "Duplicate entry '1' UNION SELECT password FROM users--' for key 'PRIMARY'"),
            (1406, "Data too long for column 'hostname'"),
            (1452, "FK fails (`db`.`t` CONSTRAINT `fk`)"),
            (1234, 'Traceback (most recent call last):\n File "/secret/app.py"\nSELECT * FROM users'),
        ]
        for errno, msg in payloads:
            info = _info(errno, msg, acao="salvar o blueprint e gerar o CSV")
            low = info.user_message.lower()
            self.assertNotIn("select ", low, msg)
            self.assertNotIn("traceback", low, msg)
            self.assertNotIn("/secret", info.user_message, msg)
            self.assertNotIn("<script", low, msg)
            self.assertNotIn("\n", info.log_message)

    def test_valor_duplicado_generico_nao_vai_ao_usuario(self):
        info = _info(
            1062,
            "Duplicate entry 'senha-secreta' for key 'links.uq_algo'",
        )
        self.assertNotIn("senha-secreta", info.user_message)
        self.assertIn("senha-secreta", info.log_message)


if __name__ == "__main__":
    unittest.main()
