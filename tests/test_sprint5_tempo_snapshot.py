"""Testes Sprint 5 — snapshot de tempos (P0-02)."""

from __future__ import annotations

import os
import unittest
from unittest import mock


class TempoSnapshotFlagsTests(unittest.TestCase):
    def test_flags_default_off(self):
        from prodesp.prodesp.tempo_snapshot import read_enabled, write_enabled

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PRODESP_TEMPO_SNAPSHOT_WRITE", None)
            os.environ.pop("PRODESP_TEMPO_SNAPSHOT_READ", None)
            self.assertFalse(write_enabled())
            self.assertFalse(read_enabled())

    def test_tempo_source_switches(self):
        from prodesp.prodesp.tempo_snapshot import TABLE, VIEW, tempo_source_table

        with mock.patch.dict(os.environ, {"PRODESP_TEMPO_SNAPSHOT_READ": "0"}):
            self.assertEqual(tempo_source_table(), VIEW)

        with mock.patch.dict(os.environ, {"PRODESP_TEMPO_SNAPSHOT_READ": "1"}):
            self.assertEqual(tempo_source_table(), TABLE)

    def test_refresh_one_noop_when_write_off(self):
        from prodesp.prodesp.tempo_snapshot import refresh_one

        cur = mock.Mock()
        with mock.patch.dict(os.environ, {"PRODESP_TEMPO_SNAPSHOT_WRITE": "0"}):
            self.assertFalse(refresh_one(cur, 42))
            cur.execute.assert_not_called()

    def test_refresh_one_executes_when_write_on(self):
        from prodesp.prodesp.tempo_snapshot import TABLE, refresh_one

        cur = mock.Mock()
        with mock.patch.dict(os.environ, {"PRODESP_TEMPO_SNAPSHOT_WRITE": "1"}):
            self.assertTrue(refresh_one(cur, 99))
            cur.execute.assert_called_once()
            sql, params = cur.execute.call_args[0]
            self.assertIn(TABLE, sql)
            self.assertIn("ON DUPLICATE KEY UPDATE", sql)
            self.assertEqual(params, (99,))

    def test_list_sql_joins_snapshot_when_read_on(self):
        from prodesp.prodesp.atendimentos_list_query import sql_list_base_from

        with mock.patch.dict(
            os.environ,
            {
                "PRODESP_TEMPO_SNAPSHOT_READ": "0",
                "PRODESP_SUBSTATUS_DESDE_READ": "0",
            },
        ):
            sql = sql_list_base_from()
            self.assertIn("vw_tempo_atendimento_detalhado", sql)
            self.assertNotIn("atendimento_tempo_snapshot", sql)

        with mock.patch.dict(
            os.environ,
            {
                "PRODESP_TEMPO_SNAPSHOT_READ": "1",
                "PRODESP_SUBSTATUS_DESDE_READ": "0",
            },
        ):
            sql = sql_list_base_from()
            self.assertIn("atendimento_tempo_snapshot", sql)
            self.assertNotIn("vw_tempo_atendimento_detalhado", sql)

    def test_tempos_etapa_uses_tempo_source(self):
        """KPIs de etapa dependem de tempo_source_table (mesmo switch da lista)."""
        from prodesp.prodesp.tempo_snapshot import TABLE, VIEW, tempo_source_table

        with mock.patch.dict(os.environ, {"PRODESP_TEMPO_SNAPSHOT_READ": "0"}):
            self.assertEqual(tempo_source_table(), VIEW)
        with mock.patch.dict(os.environ, {"PRODESP_TEMPO_SNAPSHOT_READ": "1"}):
            self.assertEqual(tempo_source_table(), TABLE)


if __name__ == "__main__":
    unittest.main()
