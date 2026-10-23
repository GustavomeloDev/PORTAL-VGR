"""Testes — contador data_revision PRODESP."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest import mock

from prodesp.prodesp import data_revision


class TestDataRevision:
    def setup_method(self):
        self._prev_path = data_revision._REV_PATH
        self._prev_dirty = data_revision._DIRTY_PATH
        fd, name = tempfile.mkstemp(prefix="prodesp_rev_test_")
        os.close(fd)
        fd2, name2 = tempfile.mkstemp(prefix="prodesp_rev_dirty_")
        os.close(fd2)
        data_revision._REV_PATH = Path(name)
        data_revision._DIRTY_PATH = Path(name2)
        data_revision.reset_for_tests(0)

    def teardown_method(self):
        try:
            data_revision.reset_for_tests(0)
        except Exception:
            pass
        try:
            data_revision._REV_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            data_revision._DIRTY_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        data_revision._REV_PATH = self._prev_path
        data_revision._DIRTY_PATH = self._prev_dirty
        with data_revision._LOCK:
            data_revision._REVISION = 0

    def test_bump_increments(self):
        assert data_revision.current_revision() == 0
        assert data_revision.bump() == 1
        assert data_revision.current_revision() == 1

    def test_bump_persists_to_file(self):
        data_revision.bump()
        data_revision.bump()
        assert data_revision._REV_PATH.read_text(encoding="utf-8").strip() == "2"

    def test_revision_payload_fields(self):
        data_revision.bump()
        payload = data_revision.revision_payload()
        assert payload["data_revision"] == 1
        assert payload["revision"] == 1
        assert "server_time" in payload
        assert payload["sync_interval_sec"] >= 15
        assert payload["next_sync_epoch_ms"] > 0

    def test_attach_to_payload(self):
        data_revision.bump()
        out = data_revision.attach_to_payload({"ok": True})
        assert out["ok"] is True
        assert out["data_revision"] == 1
        assert "server_time" in out

    def test_sync_interval_from_env(self):
        with mock.patch.dict(os.environ, {"PRODESP_DT_SYNC_INTERVAL_SEC": "120"}):
            payload = data_revision.revision_payload()
            assert payload["sync_interval_sec"] == 120

    def test_bump_with_ids_dirty_since(self):
        data_revision.bump(atendimento_ids=[10, 20])
        data_revision.bump(atendimento_ids=[20, 30])
        info = data_revision.dirty_ids_since(0)
        assert info["unchanged"] is False
        assert info["fallback_full"] is False
        assert info["ids"] == [10, 20, 30]
        assert info["data_revision"] == 2

    def test_bump_opaque_forces_fallback(self):
        data_revision.bump(atendimento_ids=[1])
        data_revision.bump()  # opaco
        info = data_revision.dirty_ids_since(0)
        assert info["fallback_full"] is True

    def test_dirty_unchanged_when_caught_up(self):
        data_revision.bump(atendimento_ids=[5])
        rev = data_revision.current_revision()
        info = data_revision.dirty_ids_since(rev)
        assert info["unchanged"] is True
        assert info["ids"] == []
