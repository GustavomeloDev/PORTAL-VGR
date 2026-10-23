"""
Validação de número de série Fortinet/FortiGate (núcleo reutilizável).

Catálogo de modelos: estender ``FORTINET_MODEL_FRAGMENTS_ORDERED`` quando
entrarem novos SKUs (ex.: 100G). Outros vendors → registry futuro separado.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional, Sequence

# (fragmento no serial, mais específico → mais curto). Fonte alinhada à família
# usada em blueprint/PRODESP; sem dependência de módulo.
FORTINET_MODEL_FRAGMENTS_ORDERED: tuple[str, ...] = (
    "900G",
    "400F",
    "200F",
    "120G",
    "100F",
    "90G",
    "80F",
    "70F",
    "60F",
    "40F",
)

# Rótulos de modelo alinhados aos fragments (inferência a partir do serial).
FORTINET_MODEL_LABELS: dict[str, str] = {
    "900G": "FortiGate 900G",
    "400F": "FortiGate 400F",
    "200F": "FortiGate 200F",
    "120G": "FortiGate 120G",
    "100F": "FortiGate 100F",
    "90G": "FortiGate 90G",
    "80F": "FortiGate 80F",
    "70F": "FortiGate 70F",
    "60F": "FortiGate 60F",
    "40F": "FortiGate 40F",
}

DEFAULT_MODELO_FORTIGATE = "FortiGate 40F"

_FAKE_SERIALS = frozenset(
    {
        "123",
        "1234",
        "12345",
        "123456",
        "000",
        "0000",
        "0",
        "1",
        "12",
        "999",
        "TEST",
        "TESTE",
        "TEMP",
        "PROVISORIO",
        "PROVISÓRIO",
        "N/A",
        "NA",
        "XXX",
        "XXXX",
        "SERIAL",
        "SERIALNUM",
        "FGT40F",
        "FGT60F",
    }
)

_VENDOR_MARKERS = (
    "fortinet",
    "fortigate",
    "forti-gate",
    "forti gate",
)


def normalizar_serial(value: Any) -> str:
    """Maiúsculas, sem espaço/hífen (colagem FG-40FTK… / FGT40F-TK…)."""
    return re.sub(r"[\s\-]+", "", str(value or "").strip()).upper()


def fortinet_model_fragments(
    extra: Sequence[str] | None = None,
) -> tuple[str, ...]:
    """Lista efetiva de fragmentos (base + extras, sem duplicar, ordem preservada)."""
    seen: set[str] = set()
    out: list[str] = []
    for frag in list(FORTINET_MODEL_FRAGMENTS_ORDERED) + list(extra or ()):
        f = str(frag or "").strip().upper()
        if not f or f in seen:
            continue
        seen.add(f)
        out.append(f)
    return tuple(out)


def _compile_serial_regex(fragments: Sequence[str]) -> re.Pattern[str]:
    alt = "|".join(re.escape(f) for f in fragments) or "40F"
    # Inventário real (PRODESP + DMA): FGT40FTK + 8 / FG120GTK + 8 (16 chars).
    return re.compile(rf"^(?:FGT|FG)(?:{alt})TK[A-Z0-9]{{8}}$", re.IGNORECASE)


def serial_fortinet_valido(
    value: Any,
    *,
    extra_model_fragments: Sequence[str] | None = None,
) -> bool:
    s = normalizar_serial(value)
    if not s or s in _FAKE_SERIALS:
        return False
    if "XXX" in s:
        return False
    if s.isdigit() and len(s) <= 8:
        return False
    regex = _compile_serial_regex(fortinet_model_fragments(extra_model_fragments))
    return bool(regex.match(s))


def validate_serial_fortinet_format(
    value: Any,
    *,
    obrigatorio: bool = True,
    extra_model_fragments: Sequence[str] | None = None,
) -> Optional[str]:
    """
    Retorna mensagem de erro ou None se ok.
    Mensagem neutra (sem status de atendimento / blueprint).
    """
    s = normalizar_serial(value)
    if not s:
        if obrigatorio:
            return (
                "Cadastre o número de série real do FortiGate "
                "(não use valor provisório)."
            )
        return None
    if serial_fortinet_valido(s, extra_model_fragments=extra_model_fragments):
        return None
    return (
        f"Número de série «{s}» inválido ou provisório. "
        "Informe o serial Fortinet no padrão do inventário "
        "(FGT40FTK… / FGT60FTK… / FG120GTK… com 8 caracteres após TK, "
        "ex.: FGT40FTK2409D6QK ou FG120GTK25006244)."
    )


def msg_serial_duplicado_global(serial: Any) -> str:
    """Unicidade global de serial — sem nome de outra unidade/cliente."""
    s = normalizar_serial(serial)
    if not s:
        return "Este serial já está cadastrado em outro equipamento."
    return f"O serial «{s}» já está cadastrado em outro equipamento."


def is_fortinet_family(
    vendor: Any = None,
    modelo: Any = None,
    *,
    extra_markers: Iterable[str] | None = None,
) -> bool:
    """True se vendor/modelo indicam Fortinet ou FortiGate."""
    blob = f"{vendor or ''} {modelo or ''}".strip().lower()
    if not blob:
        return False
    markers = list(_VENDOR_MARKERS) + [str(m).lower() for m in (extra_markers or ())]
    return any(m in blob for m in markers if m)


def fortinet_modelo_fragment(
    raw: Any,
    extra_model_fragments: Sequence[str] | None = None,
) -> str:
    """Fragmento canônico (40F, 120G) a partir de serial, FG 40F ou FortiGate 40F."""
    compact = re.sub(r"[^A-Z0-9]", "", str(raw or "").strip().upper())
    if not compact:
        return ""
    for frag in fortinet_model_fragments(extra_model_fragments):
        if frag in compact:
            return frag
    return ""


def normalize_modelo_fortigate(
    raw: Any,
    extra_model_fragments: Sequence[str] | None = None,
) -> str:
    """FG 40F / FG-40F / FortiGate 40F → FortiGate 40F. Sem fragmento conhecido, devolve o texto."""
    frag = fortinet_modelo_fragment(raw, extra_model_fragments)
    if frag:
        return FORTINET_MODEL_LABELS.get(frag) or f"FortiGate {frag}"
    return str(raw or "").strip()


def allowed_modelos_fortigate(
    extra_labels: Sequence[str] | None = None,
) -> frozenset[str]:
    labels = set(FORTINET_MODEL_LABELS.values())
    for item in extra_labels or ():
        s = str(item or "").strip()
        if s:
            labels.add(s)
    return frozenset(labels)


def infer_modelo_from_serial(
    serial: Any,
    *,
    extra_model_fragments: Sequence[str] | None = None,
    default: str | None = DEFAULT_MODELO_FORTIGATE,
    strict: bool = False,
) -> str:
    """
    Deriva rótulo de modelo a partir do serial (ex.: FGT40FTK… → FortiGate 40F).
    Fragments extras usam rótulo «FortiGate {frag}» se não estiverem no mapa.
    ``strict=True`` devolve vazio quando o serial não contém fragmento conhecido.
    """
    s = normalizar_serial(serial)
    if not s:
        return ""
    for frag in fortinet_model_fragments(extra_model_fragments):
        if frag in s:
            return FORTINET_MODEL_LABELS.get(frag) or f"FortiGate {frag}"
    if strict:
        return ""
    return default or ""


def resolve_modelo_equipamento(
    serial: Any,
    requested: Any = None,
    *,
    extra_model_fragments: Sequence[str] | None = None,
    extra_labels: Sequence[str] | None = None,
    default: str | None = DEFAULT_MODELO_FORTIGATE,
) -> tuple[str, Optional[str]]:
    """
    Modelo vem do serial quando há fragmento conhecido; senão só whitelist oficial.
    Aliases (FG 40F) são normalizados para o rótulo FortiGate.
    """
    inferred = infer_modelo_from_serial(
        serial,
        extra_model_fragments=extra_model_fragments,
        default=None,
        strict=True,
    )
    if inferred:
        return inferred, None
    req = normalize_modelo_fortigate(requested, extra_model_fragments)
    if not req:
        return default or "", None
    allowed = allowed_modelos_fortigate(extra_labels)
    if req not in allowed:
        original = str(requested or "").strip()
        return "", (
            f"Modelo «{original}» não permitido. Use o serial Fortinet "
            "(mapeia o modelo) ou selecione um modelo da lista oficial."
        )
    return req, None

