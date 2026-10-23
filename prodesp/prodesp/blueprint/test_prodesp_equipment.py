"""Testes de inferência de modelo a partir do serial (FortiGate).

Rodar:

    .venv_portal_pessoal\\Scripts\\python.exe -m pytest prodesp/prodesp/blueprint/test_prodesp_equipment.py -q
"""
from prodesp.prodesp.blueprint.prodesp_equipment import (
    infer_modelo_equipamento_from_serial,
    resolve_fortigate_model_fragment,
)


def test_infer_modelo_40f_from_serial():
    assert infer_modelo_equipamento_from_serial("FGT40FTK25008428") == "FortiGate 40F"


def test_infer_modelo_120g_from_serial_fg():
    assert infer_modelo_equipamento_from_serial("FG120GTK25006244") == "FortiGate 120G"
    assert resolve_fortigate_model_fragment(None, "FG120GTK25004510") == "120G"


def test_infer_modelo_vazio_sem_serial():
    assert infer_modelo_equipamento_from_serial("") == ""
    assert infer_modelo_equipamento_from_serial(None) == ""


def test_infer_modelo_fallback():
    assert infer_modelo_equipamento_from_serial("FGTUNKNOWN123") == "FortiGate 40F"


def test_resolve_fragment_from_modelo():
    assert resolve_fortigate_model_fragment("FortiGate 60F") == "60F"
    assert resolve_fortigate_model_fragment("FortiGate 40F") == "40F"
    assert resolve_fortigate_model_fragment(None, "FGT60FTK1") == "60F"
    assert resolve_fortigate_model_fragment(None, None) == "40F"
