"""Testes Sprint 4 — materialização substatus_desde."""

from __future__ import annotations

import os
import unittest
from datetime import datetime
from unittest import mock


class SubstatusMaterializadoFlagsTests(unittest.TestCase):
    def test_apply_stamp_on_updates(self):
        from prodesp.prodesp.substatus_materializado import (
            COLUMN,
            apply_stamp_on_updates,
        )

        updates = {"substatus_atendimentos": "Triagem"}
        with mock.patch.dict(os.environ, {"PRODESP_SUBSTATUS_DESDE_WRITE": "1"}):
            apply_stamp_on_updates(updates, substatus_mudou=True, now=datetime(2026, 7, 14, 10, 0, 0))
            self.assertIn(COLUMN, updates)
            self.assertEqual(updates[COLUMN], datetime(2026, 7, 14, 10, 0, 0))

        updates2 = {}
        with mock.patch.dict(os.environ, {"PRODESP_SUBSTATUS_DESDE_WRITE": "0"}):
            apply_stamp_on_updates(updates2, substatus_mudou=True)
            self.assertNotIn(COLUMN, updates2)

    def test_restart_timer_stamps(self):
        from prodesp.prodesp.substatus_materializado import COLUMN, apply_stamp_on_updates

        updates = {}
        with mock.patch.dict(os.environ, {"PRODESP_SUBSTATUS_DESDE_WRITE": "true"}):
            apply_stamp_on_updates(updates, substatus_mudou=False, restart_timer=True)
            self.assertIn(COLUMN, updates)

    def test_list_sql_switches(self):
        from prodesp.prodesp.atendimentos_list_query import sql_list_base_from

        with mock.patch.dict(os.environ, {"PRODESP_SUBSTATUS_DESDE_READ": "0"}):
            sql = sql_list_base_from()
            self.assertIn("ult_sub_log_agg", sql)
            self.assertNotIn("substatus_desde_atendimentos", sql)

        with mock.patch.dict(os.environ, {"PRODESP_SUBSTATUS_DESDE_READ": "1"}):
            sql = sql_list_base_from()
            self.assertIn("substatus_desde_atendimentos", sql)
            self.assertNotIn("ult_sub_log_agg", sql)


if __name__ == "__main__":
    unittest.main()
