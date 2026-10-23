"""Isola os testes de reports da tabela ``kvs`` real (webhooks, blacklist, personalização)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def kvs_fake(monkeypatch):
    from core.reports import report_settings
    from login.models import LoginDynamicSettings

    dados: dict[str, str] = {}

    def _set(key, value):
        if key not in LoginDynamicSettings.ALL_KEYS:
            raise ValueError(f"Chave dinamica invalida: {key}")
        dados[key] = "" if value is None else str(value)
        return True

    def _set_many(updates):
        for k, v in (updates or {}).items():
            _set(k, v)
        return True

    monkeypatch.setattr(LoginDynamicSettings, "_reload_cache", staticmethod(lambda force=False: dados))
    monkeypatch.setattr(LoginDynamicSettings, "set", staticmethod(_set))
    monkeypatch.setattr(LoginDynamicSettings, "set_many", staticmethod(_set_many))
    monkeypatch.setattr(LoginDynamicSettings, "ensure_table", staticmethod(lambda conn=None: None))
    report_settings.limpar_fingerprints()
    yield dados
    report_settings.limpar_fingerprints()
