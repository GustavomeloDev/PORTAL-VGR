"""Catálogo de regras de secretaria para Device Blueprint / CSV PRODESP.

Runtime resolve via ``resolve_rule`` (DB cache ou catálogo de teste).
Seed embutido espelha ``prodesp/sql/021_blueprint_secretaria_catalog.sql``.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable, Mapping, Optional

# Device padrão quando acrônimo não está no catálogo (ou inativo).
DEFAULT_DEVICE_BLUEPRINT = "BP_OES_40F"

_ACRONIMO_RE = re.compile(r"^[A-Z0-9À-Ú][A-Z0-9À-Ú\-_/]{0,38}$", re.UNICODE)
_TEMPLATE_RE = re.compile(r"^[A-Za-z0-9_\-.]{1,255}$")
_LAYOUTS = frozenset({"rede_lan", "legado"})
_REDE_REGRAS = frozenset({"nova", "antiga"})

CACHE_TTL_SEC = 60.0


@dataclass(frozen=True)
class BlueprintSecretariaRule:
    acronimo: str
    device_blueprint_template: str
    layout_csv: str = "rede_lan"  # rede_lan | legado
    rede_lan_regra: str = "nova"  # nova | antiga
    aplica_sufixo_lan_dinamico: bool = True
    dhcp_lan_start_octeto: Optional[str] = None
    dhcp_lan_end_octeto: Optional[str] = None
    emite_dhcp_server_1: bool = False
    legado_omitir_dhcp_server: bool = False
    mostrar_em_hint_ui: bool = True
    ativo: bool = True
    nome_exibicao: Optional[str] = None
    observacao: Optional[str] = None
    id: Optional[int] = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    updated_by: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def has_custom_device(self) -> bool:
        return bool(self.device_blueprint_template)


def normalize_acronimo(value: Any) -> str:
    return (str(value) if value is not None else "").strip().upper()


def validate_acronimo_token(raw: str, *, kind: str = "acrônimo") -> tuple[Optional[str], Optional[str]]:
    """Return (normalized, error_message)."""
    acr = normalize_acronimo(raw)
    if not acr:
        return None, f"{kind} obrigatório."
    if len(acr) > 40:
        return None, f"{kind} excede 40 caracteres."
    if not _ACRONIMO_RE.match(acr):
        return None, f"{kind} inválido (use letras, números, hífen)."
    return acr, None


def validate_template(raw: Any) -> tuple[Optional[str], Optional[str]]:
    tpl = (str(raw) if raw is not None else "").strip()
    if not tpl:
        return None, "Device Blueprint template obrigatório."
    if len(tpl) > 255:
        return None, "Template excede 255 caracteres."
    if not _TEMPLATE_RE.match(tpl):
        return None, "Template inválido (use A-Z, 0-9, _, -, .)."
    return tpl, None


def validate_layout(raw: Any) -> tuple[Optional[str], Optional[str]]:
    v = (str(raw) if raw is not None else "rede_lan").strip().lower()
    if v not in _LAYOUTS:
        return None, "layout_csv deve ser rede_lan ou legado."
    return v, None


def validate_rede_regra(raw: Any) -> tuple[Optional[str], Optional[str]]:
    v = (str(raw) if raw is not None else "nova").strip().lower()
    if v in ("old", "legado"):
        v = "antiga"
    if v not in _REDE_REGRAS:
        return None, "rede_lan_regra deve ser nova ou antiga."
    return v, None


def validate_dhcp_octeto(raw: Any, label: str) -> tuple[Optional[str], Optional[str]]:
    if raw is None or str(raw).strip() == "":
        return None, None
    s = str(raw).strip()
    try:
        n = int(s)
    except (TypeError, ValueError):
        return None, f"{label} inválido."
    if n < 0 or n > 255:
        return None, f"{label} deve ser 0–255."
    return str(n), None


def parse_aliases_field(raw: Any) -> tuple[list[str], Optional[str]]:
    """Aceita lista, string com vírgula/linha ou espaços."""
    if raw is None or raw == "":
        return [], None
    if isinstance(raw, (list, tuple)):
        tokens = [str(x) for x in raw]
    else:
        text = str(raw).replace(";", ",").replace("\n", ",")
        tokens = text.split(",")
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        a, err = validate_acronimo_token(t, kind="alias")
        if err and t.strip():
            return [], err
        if not a:
            continue
        if a in seen:
            continue
        seen.add(a)
        out.append(a)
    return out, None


def rule_from_row(row: Mapping[str, Any], aliases: Iterable[str] = ()) -> BlueprintSecretariaRule:
    return BlueprintSecretariaRule(
        id=int(row["id"]) if row.get("id") is not None else None,
        acronimo=normalize_acronimo(row.get("acronimo")),
        nome_exibicao=(str(row["nome_exibicao"]).strip() if row.get("nome_exibicao") else None),
        ativo=bool(int(row.get("ativo", 1) or 0)),
        device_blueprint_template=str(row.get("device_blueprint_template") or "").strip(),
        layout_csv=str(row.get("layout_csv") or "rede_lan").strip().lower(),
        rede_lan_regra=str(row.get("rede_lan_regra") or "nova").strip().lower(),
        aplica_sufixo_lan_dinamico=bool(int(row.get("aplica_sufixo_lan_dinamico", 1) or 0)),
        dhcp_lan_start_octeto=(
            str(row["dhcp_lan_start_octeto"]).strip()
            if row.get("dhcp_lan_start_octeto") not in (None, "")
            else None
        ),
        dhcp_lan_end_octeto=(
            str(row["dhcp_lan_end_octeto"]).strip()
            if row.get("dhcp_lan_end_octeto") not in (None, "")
            else None
        ),
        emite_dhcp_server_1=bool(int(row.get("emite_dhcp_server_1", 0) or 0)),
        legado_omitir_dhcp_server=bool(int(row.get("legado_omitir_dhcp_server", 0) or 0)),
        mostrar_em_hint_ui=bool(int(row.get("mostrar_em_hint_ui", 1) or 0)),
        observacao=(str(row["observacao"]).strip() if row.get("observacao") else None),
        aliases=tuple(sorted({normalize_acronimo(a) for a in aliases if a})),
        updated_by=(str(row["updated_by"]) if row.get("updated_by") else None),
        updated_at=str(row["updated_at"]) if row.get("updated_at") is not None else None,
    )


def rule_to_public_dict(rule: BlueprintSecretariaRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "acronimo": rule.acronimo,
        "nome_exibicao": rule.nome_exibicao,
        "ativo": rule.ativo,
        "device_blueprint_template": rule.device_blueprint_template,
        "layout_csv": rule.layout_csv,
        "rede_lan_regra": rule.rede_lan_regra,
        "aplica_sufixo_lan_dinamico": rule.aplica_sufixo_lan_dinamico,
        "dhcp_lan_start_octeto": rule.dhcp_lan_start_octeto,
        "dhcp_lan_end_octeto": rule.dhcp_lan_end_octeto,
        "emite_dhcp_server_1": rule.emite_dhcp_server_1,
        "legado_omitir_dhcp_server": rule.legado_omitir_dhcp_server,
        "mostrar_em_hint_ui": rule.mostrar_em_hint_ui,
        "observacao": rule.observacao,
        "aliases": list(rule.aliases),
        "updated_by": rule.updated_by,
        "updated_at": rule.updated_at,
    }


# --- Seed embutido (espelha migration 021; usado em testes e fallback de dev) ---

def _seed_rule(
    acronimo: str,
    template: str,
    *,
    layout: str = "rede_lan",
    rede: str = "nova",
    sufixo: bool = True,
    dhcp: tuple[Optional[str], Optional[str]] = (None, None),
    dhcp_srv1: bool = False,
    omit_dhcp_legado: bool = False,
    aliases: tuple[str, ...] = (),
    nome: Optional[str] = None,
    obs: Optional[str] = None,
) -> BlueprintSecretariaRule:
    return BlueprintSecretariaRule(
        acronimo=acronimo,
        nome_exibicao=nome or acronimo,
        device_blueprint_template=template,
        layout_csv=layout,
        rede_lan_regra=rede,
        aplica_sufixo_lan_dinamico=sufixo,
        dhcp_lan_start_octeto=dhcp[0],
        dhcp_lan_end_octeto=dhcp[1],
        emite_dhcp_server_1=dhcp_srv1,
        legado_omitir_dhcp_server=omit_dhcp_legado,
        aliases=aliases,
        observacao=obs,
    )


BUILTIN_SEED_RULES: tuple[BlueprintSecretariaRule, ...] = (
    _seed_rule("DETRAN", "DETRAN_HUB-C3-C4_40F_REDE_LAN_1"),
    _seed_rule("DPESP", "DPESP_HUB-C3-C4_40F_REDE_LAN_1"),
    _seed_rule("SELJ", "SE_HUB-C3-C4_40F_REDE_LAN_1", obs="Template device SE_…"),
    _seed_rule("SAP", "SAP_HUB-C3-C4_40F_REDE_LAN_1", dhcp_srv1=True),
    _seed_rule(
        "SAPTELE",
        "SAP-TELE_HUB-C5-C6_40F_REDE_LAN_1",
        dhcp_srv1=True,
        aliases=("SAP-TELE",),
        obs="Hub C5-C6; alias SAP-TELE; emite dhcp_server_1",
    ),
    _seed_rule("DER", "DER_HUB-C3-C4_40F_REDE_LAN_1"),
    _seed_rule("SDE", "SDE_HUB-C3-C4_40F_REDE_LAN_1"),
    _seed_rule(
        "SEDS",
        "SEDS_HUB-C3-C4_40F_REDE_LAN_1",
        rede="antiga",
        dhcp=("10", "60"),
        obs="Rede .0 + DHCP LAN .10–.60",
    ),
    _seed_rule("PROCON", "PROCOM_HUB-C3-C4_40F_REDE_LAN_1", obs="Template PROCOM_…"),
    _seed_rule(
        "PRO-SANGUE",
        "PROSANGUE_HUB-C3-C4_40F_REDE_LAN_1",
        aliases=("PROSANGUE",),
    ),
    _seed_rule(
        "SP-AGUAS",
        "SPAGUAS_HUB-C3-C4_40F_REDE_LAN_1",
        aliases=("SPAGUAS",),
    ),
    _seed_rule("CEETEPS", "BP_CEETEPS_HUB-C3-C4_40F_REDE_LAN_1_VLAN_VOZ"),
    _seed_rule("POUPATEMPO", "PPT_HUB-C3-C4_40F_REDE_LAN_VOZ", sufixo=False),
    _seed_rule(
        "DIPOL",
        "PCSPO_HUB-C3-C4_40F_REDE_LAN_1",
        layout="legado",
        omit_dhcp_legado=True,
    ),
    _seed_rule("PGE", "PGE_HUB-C3-C4_HSW_40F_REDE_LAN_1"),
    _seed_rule("TJSP", "TJ_HUB-C1-C2_60F_REDE_LAN_1_VOZ_WIFI"),
    _seed_rule("CDHU", "CDHU_HUB-C3-C4_40F_REDE_LAN_1"),
    _seed_rule(
        "JUSTICA",
        "SJC_HUB-C3-C4_40F_REDE_LAN_1_VLAN_VOZ_ASSOC",
        nome="JUSTIÇA",
        aliases=("JUSTIÇA",),
    ),
    _seed_rule("FLORESTAL", "FLORESTAL_HUB-C1-C2_40F_REDE_LAN_1"),
)

# Templates do seed (asserts / smoke). Fonte viva em runtime = MySQL via resolve_rule.
DETRAN_DEVICE_BLUEPRINT = "DETRAN_HUB-C3-C4_40F_REDE_LAN_1"
DPESP_DEVICE_BLUEPRINT = "DPESP_HUB-C3-C4_40F_REDE_LAN_1"
SELJ_DEVICE_BLUEPRINT = "SE_HUB-C3-C4_40F_REDE_LAN_1"
SAP_DEVICE_BLUEPRINT = "SAP_HUB-C3-C4_40F_REDE_LAN_1"
SAPTELE_DEVICE_BLUEPRINT = "SAP-TELE_HUB-C5-C6_40F_REDE_LAN_1"
DER_DEVICE_BLUEPRINT = "DER_HUB-C3-C4_40F_REDE_LAN_1"
SDE_DEVICE_BLUEPRINT = "SDE_HUB-C3-C4_40F_REDE_LAN_1"
SEDS_DEVICE_BLUEPRINT = "SEDS_HUB-C3-C4_40F_REDE_LAN_1"
PROCON_DEVICE_BLUEPRINT = "PROCOM_HUB-C3-C4_40F_REDE_LAN_1"
PROSANGUE_DEVICE_BLUEPRINT = "PROSANGUE_HUB-C3-C4_40F_REDE_LAN_1"
SPAGUAS_DEVICE_BLUEPRINT = "SPAGUAS_HUB-C3-C4_40F_REDE_LAN_1"
CEETEPS_DEVICE_BLUEPRINT = "BP_CEETEPS_HUB-C3-C4_40F_REDE_LAN_1_VLAN_VOZ"
POUPATEMPO_DEVICE_BLUEPRINT = "PPT_HUB-C3-C4_40F_REDE_LAN_VOZ"
DIPOL_DEVICE_BLUEPRINT = "PCSPO_HUB-C3-C4_40F_REDE_LAN_1"
PGE_DEVICE_BLUEPRINT = "PGE_HUB-C3-C4_HSW_40F_REDE_LAN_1"
TJSP_DEVICE_BLUEPRINT = "TJ_HUB-C1-C2_60F_REDE_LAN_1_VOZ_WIFI"
CDHU_DEVICE_BLUEPRINT = "CDHU_HUB-C3-C4_40F_REDE_LAN_1"
JUSTICA_DEVICE_BLUEPRINT = "SJC_HUB-C3-C4_40F_REDE_LAN_1_VLAN_VOZ_ASSOC"
FLORESTAL_DEVICE_BLUEPRINT = "FLORESTAL_HUB-C1-C2_40F_REDE_LAN_1"


class StaticCatalog:
    """Mapa acrônimo/alias → regra (somente ativas resolvidas)."""

    def __init__(self, rules: Iterable[BlueprintSecretariaRule]):
        self._by_key: dict[str, BlueprintSecretariaRule] = {}
        self._all: list[BlueprintSecretariaRule] = []
        for r in rules:
            self._all.append(r)
            if not r.ativo:
                continue
            self._by_key[r.acronimo] = r
            for a in r.aliases:
                self._by_key[normalize_acronimo(a)] = r

    def resolve(self, acronimo: str) -> Optional[BlueprintSecretariaRule]:
        key = normalize_acronimo(acronimo)
        if not key:
            return None
        return self._by_key.get(key)

    def list_rules(self, *, only_active: bool = False, only_hints: bool = False) -> list[BlueprintSecretariaRule]:
        rows = self._all
        if only_active:
            rows = [r for r in rows if r.ativo]
        if only_hints:
            rows = [r for r in rows if r.mostrar_em_hint_ui and r.ativo]
        return list(rows)


# --- Resolução global (teste ou DB) ---

_lock = threading.RLock()
_test_catalog: Optional[StaticCatalog] = None
_db_loader: Optional[Callable[[], StaticCatalog]] = None
_db_cache: Optional[StaticCatalog] = None
_db_cache_at: float = 0.0
_db_cache_error_logged: bool = False


def install_test_catalog(rules: Optional[Iterable[BlueprintSecretariaRule]] = None) -> StaticCatalog:
    """Instala catálogo estático (seed por padrão). Usado nos testes."""
    global _test_catalog
    cat = StaticCatalog(rules if rules is not None else BUILTIN_SEED_RULES)
    with _lock:
        _test_catalog = cat
    return cat


def clear_test_catalog() -> None:
    global _test_catalog
    with _lock:
        _test_catalog = None


def set_db_catalog_loader(loader: Optional[Callable[[], StaticCatalog]]) -> None:
    """Registra loader que consulta o MySQL (chamado pelo repo)."""
    global _db_loader
    with _lock:
        _db_loader = loader
        _invalidate_db_cache_unlocked()


def invalidate_catalog_cache() -> None:
    with _lock:
        _invalidate_db_cache_unlocked()


def _invalidate_db_cache_unlocked() -> None:
    global _db_cache, _db_cache_at
    _db_cache = None
    _db_cache_at = 0.0


def _get_db_catalog() -> Optional[StaticCatalog]:
    global _db_cache, _db_cache_at, _db_cache_error_logged
    loader = _db_loader
    if loader is None:
        return None
    now = time.monotonic()
    with _lock:
        if _db_cache is not None and (now - _db_cache_at) < CACHE_TTL_SEC:
            return _db_cache
    try:
        cat = loader()
    except Exception:
        if not _db_cache_error_logged:
            _db_cache_error_logged = True
            try:
                import logging

                logging.getLogger(__name__).exception(
                    "Falha ao carregar catálogo blueprint_secretaria; usando miss/fallback"
                )
            except Exception:
                pass
        with _lock:
            return _db_cache  # stale se existir
    with _lock:
        _db_cache = cat
        _db_cache_at = time.monotonic()
        return cat


def resolve_rule(acronimo: str) -> Optional[BlueprintSecretariaRule]:
    """Resolve regra ativa por acrônimo canônico ou alias. None → default BP_OES + layout REDE_LAN."""
    key = normalize_acronimo(acronimo)
    if not key:
        return None
    with _lock:
        test_cat = _test_catalog
    if test_cat is not None:
        return test_cat.resolve(key)
    db_cat = _get_db_catalog()
    if db_cat is not None:
        return db_cat.resolve(key)
    # Sem loader DB e sem teste: seed embutido (dev/import) — migrate aplica a fonte oficial.
    return StaticCatalog(BUILTIN_SEED_RULES).resolve(key)


def rule_for_unidade(dados_unidade: Optional[Mapping[str, Any]]) -> Optional[BlueprintSecretariaRule]:
    if not dados_unidade:
        return None
    attached = dados_unidade.get("_blueprint_rule")
    if isinstance(attached, BlueprintSecretariaRule):
        return attached if attached.ativo else None
    return resolve_rule(dados_unidade.get("acronimo_unidades"))


def list_hint_acronimos(limit: int = 12) -> list[str]:
    """Acrônimos canônicos para placeholder de UI."""
    with _lock:
        test_cat = _test_catalog
    cat = test_cat or _get_db_catalog() or StaticCatalog(BUILTIN_SEED_RULES)
    rules = cat.list_rules(only_active=True, only_hints=True)
    # Prefer common first-ish order of seed
    order = {r.acronimo: i for i, r in enumerate(BUILTIN_SEED_RULES)}
    rules.sort(key=lambda r: order.get(r.acronimo, 999))
    return [r.acronimo for r in rules[: max(0, int(limit or 0))]]


def attach_rule_to_unidade(dados_unidade: dict) -> dict:
    """Anexa rule resolvida em dados_unidade (mutável) e retorna o mesmo dict."""
    rule = resolve_rule((dados_unidade or {}).get("acronimo_unidades"))
    if rule is not None:
        dados_unidade["_blueprint_rule"] = rule
    else:
        dados_unidade.pop("_blueprint_rule", None)
    return dados_unidade


def with_inactive_disabled(rule: BlueprintSecretariaRule) -> BlueprintSecretariaRule:
    return replace(rule, ativo=False)
