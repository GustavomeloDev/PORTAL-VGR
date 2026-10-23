"""
Enriquecimento de endereço da unidade PRODESP: número (parse do logradouro),
bairro/CEP (ViaCEP → OpenCEP → BrasilAPI) e coordenadas/bairro
(Nominatim search → structured → reverse geocode).
"""
from __future__ import annotations

import functools
import re
import time
import unicodedata
from typing import Any

import requests

from core.logger import get_logger

_log = get_logger("PRODESP")

_USER_AGENT = "PortalImplantacaoPRODESP/1.0 (endereco-enriquecimento; contato TI Vivo)"

_PLACEHOLDER_RE = re.compile(
    r"^(x+|\.+|-+|n/?a|nao\s+informado.*|null|undefined|0+)$",
    re.IGNORECASE,
)

_RODOVIA_RE = re.compile(
    r"\b(rodovia|rod\.|br[-\s]?\d|sp[-\s]?\d|via\s|estrada|anel|marginal)\b",
    re.IGNORECASE,
)

_SEM_NUMERO_SUFFIX_RE = re.compile(
    r"\b0\s*(?:S/C|S\.?/C\.?|S/N|S\.?/N\.?|SN)\s*$",
    re.IGNORECASE,
)

# Municípios mais frequentes na tabela unidades (2079 registros) + grafia sem acento.
_CITY_ALIASES: dict[str, str] = {
    "SAO PAULO": "São Paulo",
    "SÃO PAULO": "São Paulo",
    "S JOSE DOS CAMPOS": "São José dos Campos",
    "SAO JOSE DOS CAMPOS": "São José dos Campos",
    "MOGI DAS CRUZES": "Mogi das Cruzes",
    "GUARULHOS": "Guarulhos",
    "OSASCO": "Osasco",
    "PIRACICABA": "Piracicaba",
    "SAO JOSE DO RIO PRETO": "São José do Rio Preto",
    "BAURU": "Bauru",
    "SAO BERNARDO DO CAMPO": "São Bernardo do Campo",
    "SANTOS": "Santos",
    "RIBEIRAO PRETO": "Ribeirão Preto",
    "ARARAQUARA": "Araraquara",
    "PRESIDENTE PRUDENTE": "Presidente Prudente",
    "ITAPETININGA": "Itapetininga",
    "AVARE": "Avaré",
    "FRANCA": "Franca",
    "SANTO ANDRE": "Santo André",
    "JUNDIAI": "Jundiaí",
    "ARACATUBA": "Araçatuba",
    "LIMEIRA": "Limeira",
    "TAUBATE": "Taubaté",
    "ITAPEVA": "Itapeva",
    "SAO CARLOS": "São Carlos",
    "CAMPINAS": "Campinas",
    "TABAPUA": "Tabapuá",
    "TABOAO DA SERRA": "Taboão da Serra",
    "COTIA": "Cotia",
    "FERRAZ DE VASCONCELOS": "Ferraz de Vasconcelos",
    "SUZANO": "Suzano",
    "SAO VICENTE": "São Vicente",
    "S VICENTE": "São Vicente",
}

# Abreviações após vírgula no logradouro (26,7% dos endereços em unidades).
_TITLE_BEFORE_NAME: dict[str, str] = {
    "DR": "Doutor",
    "CEL": "Coronel",
    "PRES": "Presidente",
    "PROF": "Professor",
    "DOM": "Dom",
    "MAL": "Marechal",
    "MAJ": "Major",
    "CAP": "Capitão",
    "ENG": "Engenheiro",
    "PE": "Padre",
    "COMDT": "Comandante",
    "VER": "Vereador",
    "TTE": "Tenente",
    "SGT": "Sargento",
    "STA": "Santa",
    "STO": "Santo",
    "CON": "Conselheiro",
    "COMEND": "Comendador",
    "CDE": "Conde",
    "DQ": "Duque",
    "DA": "Dona",
    "DEP": "Deputado",
}

_TITLE_SKIP_IN_QUERY = frozenset({"GAL", "PFTO", "BR"})

_COMMA_TITLE_RE = re.compile(
    r"^(?P<tipo>RUA|AV\.?|AVENIDA|TRAVESSA|AL\.?|ALAMEDA|ESTRADA|ROD\.?|RODOVIA)\s+"
    r"(?P<nome>.+?),\s*(?P<titulo>[A-Z]{2,6})\.?\s*(?P<num>\d+)\s*",
    re.IGNORECASE,
)

# Limites das colunas em unidades (varchar).
_FIELD_LIMITS: dict[str, int] = {
    "numero": 10,
    "bairro": 80,
    "municipio": 80,
    "estado": 2,
    "cep": 9,
    "latitude": 24,
    "longitude": 24,
}

# Similaridade mínima (tokens do logradouro) para cruzar CEP × endereço.
_LOGRADOURO_MATCH_ALTA = 0.42
_LOGRADOURO_STOP_TOKENS = frozenset(
    {
        "RUA", "AV", "AVENIDA", "ROD", "RODOVIA", "ESTRADA", "TRAVESSA", "AL", "ALAMEDA",
        "S", "C", "N", "SN", "SC", "PE", "GAL", "PFTO", "KM", "BR", "SP",
        "DE", "DA", "DO", "DOS", "DAS", "E", "EM", "NO", "NA",
    }
)

_NUMERO_SN_VALUES = frozenset({"S/N", "SN", "S/N."})

_NOMINATIM_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def is_placeholder_or_empty(val: Any) -> bool:
    s = _clean_str(val)
    if not s:
        return True
    if _PLACEHOLDER_RE.match(s):
        return True
    compact = re.sub(r"[^a-zA-Z]", "", s)
    if compact and len(compact) >= 2 and all(c.lower() == "x" for c in compact):
        return True
    return False


def is_invalid_numero(val: Any) -> bool:
    """Número 0, vazio ou placeholder não deve ser mantido/sugerido. S/N é válido."""
    if is_placeholder_or_empty(val):
        return True
    s = _clean_str(val).upper().replace(" ", "")
    if s in _NUMERO_SN_VALUES or s.replace(".", "") == "SN":
        return False
    if s in ("0", "00", "000"):
        return True
    return False


def is_sem_numero_logradouro(endereco: str) -> bool:
    """Rodovia/via com 0 S/C ou equivalente → sem número comercial."""
    s = _clean_str(endereco)
    if not s:
        return False
    if _SEM_NUMERO_SUFFIX_RE.search(s):
        return True
    if _RODOVIA_RE.search(s) and not extract_numero_from_endereco(s):
        return True
    return False


def resolve_numero_suggestion(endereco: str, numero_atual: str) -> tuple[str | None, str | None]:
    """
    Retorna (valor, fonte) para sugerir número: parse, S/N (rodovia/sem número) ou None.
    """
    if not is_invalid_numero(numero_atual):
        return None, None
    if is_sem_numero_logradouro(endereco):
        return "S/N", "sem_numero"
    extracted = extract_numero_from_endereco(endereco)
    if extracted:
        return extracted, "parse_endereco"
    return None, None


def needs_coord_fill(lat: Any, lon: Any) -> bool:
    if is_placeholder_or_empty(lat) or is_placeholder_or_empty(lon):
        return True
    try:
        la = float(str(lat).replace(",", ".").strip())
        lo = float(str(lon).replace(",", ".").strip())
        if abs(la) < 0.0001 and abs(lo) < 0.0001:
            return True
        if not (-90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0):
            return True
        return False
    except (TypeError, ValueError):
        return True


def _parse_coords(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        la = float(str(lat).replace(",", ".").strip())
        lo = float(str(lon).replace(",", ".").strip())
        if -90.0 <= la <= 90.0 and -180.0 <= lo <= 180.0 and (abs(la) > 0.0001 or abs(lo) > 0.0001):
            return la, lo
    except (TypeError, ValueError):
        pass
    return None


def extract_numero_from_endereco(endereco: str) -> str | None:
    """Extrai número provável do logradouro (ex.: 'RUA X 1435 S/C' → '1435')."""
    s = _clean_str(endereco)
    if not s:
        return None

    patterns = [
        r"\b(\d{1,6})\s*(?:S/C|S\.?/C\.?|S/N|S\.?/N\.?|SN)\s*$",
        r",\s*(?:N[º°o.]?\s*)?(\d{1,6})\s*(?:S/C|S/N|SN)?\s*$",
        r"\s+(\d{1,6})\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, s, re.IGNORECASE)
        if m:
            num = m.group(1)
            if num and num != "0":
                return num
    return None


def _normalize_cep_digits(cep: Any) -> str | None:
    digits = re.sub(r"\D+", "", _clean_str(cep))
    if len(digits) == 8:
        return digits
    if len(digits) == 9:
        # Ex.: máscara 15880-0230 → tenta os 8 primeiros dígitos
        return digits[:8]
    return None


def _cep_candidates(cep: Any) -> list[str]:
    """Gera CEPs de 8 dígitos (9→8, 7→0+7 conforme padrões em unidades)."""
    digits = re.sub(r"\D+", "", _clean_str(cep))
    seen: set[str] = set()
    out: list[str] = []

    def add(cand: str) -> None:
        if len(cand) == 8 and cand not in seen:
            seen.add(cand)
            out.append(cand)

    if len(digits) == 8:
        add(digits)
    elif len(digits) == 9:
        add(digits[:8])
        add(digits[1:9])
    elif len(digits) == 7:
        add("0" + digits)
        add(digits)
    elif digits:
        add(digits[:8])
    return out


def _municipio_lookup_key(municipio: str) -> str:
    return re.sub(r"\s+", " ", _clean_str(municipio).upper())


def _normalize_city_for_compare(city: str) -> str:
    """Compara cidades sem acento/caixa (São Vicente == SAO VICENTE)."""
    s = _clean_str(city).upper()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def _normalize_bairro_for_compare(bairro: str) -> str:
    return _normalize_city_for_compare(bairro)


def _bairros_equivalent(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return _normalize_bairro_for_compare(a) == _normalize_bairro_for_compare(b)


def _should_apply_cep_bairro(bairro_atual: str, bairro_cep: str) -> bool:
    """CEP (ViaCEP) costuma ser o bairro oficial do CEP; corrige reverso do mapa impreciso."""
    if not bairro_cep or is_placeholder_or_empty(bairro_cep):
        return False
    if is_placeholder_or_empty(bairro_atual):
        return True
    return not _bairros_equivalent(bairro_atual, bairro_cep)


def _cities_equivalent(city_a: str, city_b: str) -> bool:
    if not city_a or not city_b:
        return True
    na = _normalize_city_for_compare(city_a)
    nb = _normalize_city_for_compare(city_b)
    if na == nb:
        return True
    aliases = _city_aliases_merged()
    canon_a = _normalize_city_for_compare(aliases.get(_municipio_lookup_key(city_a), city_a))
    canon_b = _normalize_city_for_compare(aliases.get(_municipio_lookup_key(city_b), city_b))
    return canon_a == canon_b or na == canon_b or nb == canon_a


def _clamp_updates(updates: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in updates.items():
        lim = _FIELD_LIMITS.get(key)
        s = _clean_str(val)
        if lim and len(s) > lim:
            s = s[:lim]
        out[key] = s
    return out


def payload_from_unidade_row(row: dict) -> dict:
    """Monta payload da API a partir de colunas unidades.*"""
    return {
        "endereco": row.get("endereco_unidades"),
        "numero": row.get("numero_unidades"),
        "bairro": row.get("bairro_unidades"),
        "municipio": row.get("municipio_unidades"),
        "estado": row.get("estado_unidades"),
        "cep": row.get("cep_unidades"),
        "latitude": row.get("latitude_unidades"),
        "longitude": row.get("longitude_unidades"),
    }


@functools.lru_cache(maxsize=1)
def _city_aliases_merged() -> dict[str, str]:
    """Mescla aliases estáticos com chaves distintas do banco (quando disponível)."""
    merged = dict(_CITY_ALIASES)
    try:
        from prodesp.credentials.db_config import db_config

        import mysql.connector

        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT UPPER(TRIM(municipio_unidades)) FROM unidades "
            "WHERE municipio_unidades IS NOT NULL AND TRIM(municipio_unidades) <> ''"
        )
        for (mun_key,) in cur.fetchall():
            if mun_key in merged:
                continue
            if mun_key in _CITY_ALIASES:
                merged[mun_key] = _CITY_ALIASES[mun_key]
        cur.close()
        conn.close()
    except Exception as e:
        _log.debug("Nao foi possivel ler municipios do banco para aliases: %s", e)
    return merged


def _tipo_logradouro_prefix(tipo: str) -> str:
    t = tipo.upper()
    if t.startswith("RUA"):
        return "Rua"
    if t.startswith("AV"):
        return "Avenida"
    if t.startswith("EST"):
        return "Estrada"
    if t.startswith("ROD"):
        return "Rodovia"
    if t.startswith("TRA"):
        return "Travessa"
    return tipo.title()


def _expand_comma_title_variants(raw: str) -> list[str]:
    """Ex.: 'RUA CALMON,PROF 33 S/C' → 'Rua Professor Calmon 33'."""
    m = _COMMA_TITLE_RE.match(_clean_str(raw))
    if not m:
        return []
    prefix = _tipo_logradouro_prefix(m.group("tipo"))
    nome = m.group("nome").strip()
    titulo = m.group("titulo").upper()
    num = m.group("num")
    out: list[str] = []
    word = _TITLE_BEFORE_NAME.get(titulo)
    if word and titulo not in _TITLE_SKIP_IN_QUERY:
        out.append(f"{prefix} {word} {nome} {num}")
    out.append(f"{prefix} {nome} {num}")
    return out


def _fetch_cep_viacep(cep: str, timeout: float = 6.0) -> dict | None:
    try:
        r = requests.get(f"https://viacep.com.br/ws/{cep}/json/", timeout=timeout, verify=False)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("erro"):
            return None
        return data if isinstance(data, dict) else None
    except requests.RequestException as e:
        _log.warning("ViaCEP falhou cep=%s: %s", cep, e)
        return None


def _fetch_cep_opencep(cep: str, timeout: float = 6.0) -> dict | None:
    try:
        r = requests.get(f"https://opencep.com/v1/{cep}", timeout=timeout, verify=False)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None
        return {
            "logradouro": data.get("address") or data.get("logradouro"),
            "bairro": data.get("district") or data.get("bairro"),
            "localidade": data.get("city") or data.get("localidade"),
            "uf": data.get("state") or data.get("uf"),
            "cep": data.get("cep") or cep,
        }
    except requests.RequestException as e:
        _log.warning("OpenCEP falhou cep=%s: %s", cep, e)
        return None


def _fetch_cep_brasilapi(cep: str, timeout: float = 6.0) -> dict | None:
    try:
        r = requests.get(f"https://brasilapi.com.br/api/cep/v1/{cep}", timeout=timeout, verify=False)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            return None
        return {
            "logradouro": data.get("street"),
            "bairro": data.get("neighborhood"),
            "localidade": data.get("city"),
            "uf": data.get("state"),
            "cep": data.get("cep") or cep,
        }
    except requests.RequestException as e:
        _log.warning("BrasilAPI CEP falhou cep=%s: %s", cep, e)
        return None


def fetch_cep_with_fallback(cep: str) -> tuple[dict | None, str | None]:
    for name, fn in (
        ("viacep", _fetch_cep_viacep),
        ("opencep", _fetch_cep_opencep),
        ("brasilapi", _fetch_cep_brasilapi),
    ):
        data = fn(cep)
        if data:
            return data, name
        time.sleep(0.15)
    return None, None


def _row_matches_municipio(addr: dict, municipio: str) -> bool:
    if not municipio:
        return True
    for key in ("city", "town", "municipality"):
        val = _clean_str(addr.get(key))
        if val and _cities_equivalent(val, municipio):
            return True
    return False


def _pick_nominatim_row(rows: list, municipio: str, estado: str) -> dict | None:
    if not rows:
        return None
    uf = _clean_str(estado).upper()
    for row in rows:
        addr = row.get("address") or {}
        if municipio and not _row_matches_municipio(addr, municipio):
            continue
        if uf:
            state = _clean_str(addr.get("state", "")).upper()
            iso = _clean_str(addr.get("ISO3166-2-lvl4", "")).upper()
            if uf == "SP" and not (iso.endswith("-SP") or "PAULO" in state or state in ("SP",)):
                if state and state not in ("SP", "SÃO PAULO", "SAO PAULO"):
                    continue
        return row
    if municipio:
        return None
    return rows[0]


def _bairro_from_nominatim_address(addr: dict) -> str:
    if not addr:
        return ""
    for key in (
        "suburb",
        "neighbourhood",
        "quarter",
        "city_district",
        "district",
        "village",
        "hamlet",
    ):
        v = _clean_str(addr.get(key))
        if v and not is_placeholder_or_empty(v):
            return v
    return ""


def _endereco_for_geocode(endereco: str) -> str:
    """Remove sufixos S/C e S/N do logradouro para melhorar busca em geocoders."""
    s = _clean_str(endereco)
    s = re.sub(r"\s*(?:S/C|S\.?/C\.?)\s*$", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*(?:S/N|S\.?/N\.?|SN)\s*$", "", s, flags=re.IGNORECASE)
    return s.strip()


def _logradouro_tokens(text: str) -> set[str]:
    s = _normalize_city_for_compare(_endereco_for_geocode(text))
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return {
        t
        for t in s.split()
        if len(t) > 1 and t not in _LOGRADOURO_STOP_TOKENS and t != "0"
    }


def _logradouro_match_score(endereco_form: str, logradouro_cep: str) -> float:
    """0–1: compatibilidade entre endereco_unidades e logradouro retornado pelo CEP."""
    ta = _logradouro_tokens(endereco_form)
    tb = _logradouro_tokens(logradouro_cep)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    if not inter:
        return 0.0
    jaccard = len(inter) / len(ta | tb)
    smaller, larger = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    coverage = len(smaller & larger) / len(smaller)
    return max(jaccard, coverage * 0.92)


def _postcode_matches_cep(postcode: Any, cep_digits: str) -> bool:
    pc = re.sub(r"\D+", "", _clean_str(postcode))
    if len(pc) < 5 or len(cep_digits) < 5:
        return False
    return pc[:5] == cep_digits[:5] or (len(pc) >= 8 and pc[:8] == cep_digits[:8])


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import atan2, cos, radians, sin, sqrt

    r = 6371.0
    la1, lo1, la2, lo2 = map(radians, [lat1, lon1, lat2, lon2])
    x = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * r * atan2(sqrt(x), sqrt(1 - x))


def _validate_cep_endereco_cross(
    cep_data: dict,
    endereco: str,
    municipio: str,
    estado: str,
) -> dict[str, Any]:
    log_cep = _clean_str(cep_data.get("logradouro") or cep_data.get("street"))
    city_ok = _cep_data_matches_unidade(cep_data, municipio, estado)
    score = _logradouro_match_score(endereco, log_cep) if (endereco and log_cep) else 0.0
    if endereco and not log_cep:
        score = 0.35
    high = bool(city_ok and endereco and score >= _LOGRADOURO_MATCH_ALTA)
    return {
        "score": round(score, 2),
        "high_confidence": high,
        "logradouro_cep": log_cep,
        "city_ok": city_ok,
        "localidade_cep": _clean_str(cep_data.get("localidade") or cep_data.get("city")),
        "uf_cep": _clean_str(cep_data.get("uf") or cep_data.get("state")),
    }


def _should_apply_field_from_cep(current: str, cep_value: str, *, city: bool = False) -> bool:
    if not cep_value or is_placeholder_or_empty(cep_value):
        return False
    if is_placeholder_or_empty(current):
        return True
    if city:
        return not _cities_equivalent(current, cep_value)
    return _normalize_city_for_compare(current) != _normalize_city_for_compare(cep_value)


def _geocode_alta_confianca(
    logradouro: str,
    numero: str,
    municipio: str,
    estado: str,
    cep_digits: str,
    bairro_cep: str,
) -> tuple[dict | None, str | None]:
    """Busca coordenadas priorizando logradouro oficial do CEP + CEP validado."""
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", q).strip()
        if len(q) > 12 and q not in seen:
            seen.add(q)
            queries.append(q)

    uf = _clean_str(estado) or "SP"
    bairro_q = bairro_cep if bairro_cep and not is_placeholder_or_empty(bairro_cep) else ""
    for city in _city_names_for_geocode(municipio):
        if bairro_q:
            add(f"{logradouro}, {bairro_q}, {city}, {uf}, {cep_digits}, Brasil")
        add(f"{logradouro}, {city}, {uf}, {cep_digits}, Brasil")
    for street in _street_lines_for_geocode(logradouro, numero):
        for city in _city_names_for_geocode(municipio):
            add(f"{street}, {city}, {uf}, {cep_digits}, Brasil")

    geo, src = geocode_with_fallback(
        queries,
        endereco=logradouro,
        numero=numero,
        municipio=municipio,
        estado=estado,
        cep=cep_digits,
        include_cep_structured=True,
    )
    if not geo or geo.get("lat") is None:
        return None, None
    gb = _clean_str(geo.get("bairro"))
    if bairro_cep and gb and _bairros_equivalent(gb, bairro_cep):
        return geo, src
    if _postcode_matches_cep(geo.get("cep"), cep_digits):
        return geo, src
    # Rodovias: mapa pode devolver CEP de trecho vizinho; aceita se achou no município certo.
    return geo, src


def _cep_data_matches_unidade(cep_data: dict, municipio: str, estado: str) -> bool:
    """Evita usar CEP de outra cidade (ex.: 86742700 → Arapongas/PR com município Suzano/SP)."""
    if not cep_data:
        return False
    city_api = _clean_str(cep_data.get("localidade") or cep_data.get("city"))
    uf_api = _clean_str(cep_data.get("uf") or cep_data.get("state")).upper()
    city_want = _clean_str(municipio)
    uf_want = _clean_str(estado).upper()
    if uf_want and uf_api and uf_api != uf_want:
        return False
    if not city_want:
        return True
    return _cities_equivalent(city_api, city_want)


def _street_lines_for_geocode(endereco: str, numero: str) -> list[str]:
    """
    Gera linhas de logradouro para o Nominatim (vírgulas e abreviações quebram a busca).
    Baseado em padrões de endereco_unidades (S/C 88%, vírgula 27%, DR/PRES/PROF após vírgula).
    """
    raw = _clean_str(endereco)
    if not raw:
        return []

    lines: list[str] = []
    seen: set[str] = set()

    def push(s: str) -> None:
        s = re.sub(r"\s+", " ", s).strip()
        if len(s) > 3 and s not in seen:
            seen.add(s)
            lines.append(s)

    for variant in _expand_comma_title_variants(raw):
        push(variant)

    base = _endereco_for_geocode(raw)
    base = base.replace(",", " ")
    base = re.sub(r"\s+", " ", base).strip()
    push(base)

    for titulo, palavra in _TITLE_BEFORE_NAME.items():
        base_t = re.sub(rf"\b{titulo}\.?\b", palavra, base, flags=re.IGNORECASE)
        if base_t != base:
            push(base_t)

    num = _clean_str(numero)
    if num and not is_invalid_numero(num) and num.upper() not in _NUMERO_SN_VALUES:
        for line in list(lines):
            if num not in line:
                push(f"{line} {num}")

    return lines


def _city_names_for_geocode(municipio: str) -> list[str]:
    raw = _clean_str(municipio)
    if not raw:
        return []
    names: list[str] = []
    key = _municipio_lookup_key(raw)
    aliases = _city_aliases_merged()
    alias = aliases.get(key)
    if alias:
        names.append(alias)
    if raw not in names:
        names.append(raw)
    return names


def _build_geocode_queries(
    endereco: str,
    numero: str,
    municipio: str,
    estado: str,
    *,
    include_cep: bool = False,
    cep: str = "",
) -> list[str]:
    """Várias consultas: logradouro normalizado + município/UF; CEP só se validado nas bases."""
    uf = _clean_str(estado) or "SP"
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", q).strip()
        if len(q) > 12 and q not in seen:
            seen.add(q)
            queries.append(q)

    cep_part = ""
    if include_cep:
        wc = _normalize_cep_digits(cep)
        if wc:
            cep_part = f", {wc}"

    streets = _street_lines_for_geocode(endereco, numero)
    if not streets:
        streets = [_endereco_for_geocode(endereco)]

    for street in streets:
        for city in _city_names_for_geocode(municipio):
            add(f"{street}, {city}, {uf}, Brasil{cep_part}")
            add(f"{street}, {city}, Brasil{cep_part}")

    return queries


def _geocode_nominatim_search(
    query: str,
    municipio: str = "",
    estado: str = "",
    timeout: float = 10.0,
) -> dict | None:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "json", "limit": 5, "countrycodes": "br", "addressdetails": 1},
            headers=_NOMINATIM_HEADERS,
            timeout=timeout,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        row = _pick_nominatim_row(rows, municipio, estado)
        if not row:
            return None
        addr = row.get("address") or {}
        return {
            "lat": row.get("lat"),
            "lon": row.get("lon"),
            "bairro": _bairro_from_nominatim_address(addr),
            "cep": addr.get("postcode"),
            "municipio": addr.get("city") or addr.get("town") or addr.get("municipality"),
            "estado": addr.get("state"),
        }
    except requests.RequestException as e:
        _log.warning("Nominatim search falhou: %s", e)
        return None


def _geocode_nominatim_structured(
    endereco: str,
    municipio: str,
    estado: str,
    cep: str,
    numero: str = "",
    timeout: float = 10.0,
) -> dict | None:
    params: dict[str, str] = {
        "format": "json",
        "limit": "5",
        "countrycodes": "br",
        "addressdetails": "1",
    }
    street_lines = _street_lines_for_geocode(endereco, numero)
    street = street_lines[0] if street_lines else _endereco_for_geocode(endereco)
    if street:
        params["street"] = street
    city = _clean_str(municipio)
    if city:
        params["city"] = city
    state = _clean_str(estado)
    if state:
        params["state"] = state
    wc = _normalize_cep_digits(cep)
    if wc:
        params["postalcode"] = wc
    if len(params) <= 4:
        return None
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers=_NOMINATIM_HEADERS,
            timeout=timeout,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return None
        row = _pick_nominatim_row(rows, municipio, estado)
        if not row:
            return None
        addr = row.get("address") or {}
        return {
            "lat": row.get("lat"),
            "lon": row.get("lon"),
            "bairro": _bairro_from_nominatim_address(addr),
            "cep": addr.get("postcode"),
            "municipio": addr.get("city") or addr.get("town"),
            "estado": addr.get("state"),
        }
    except requests.RequestException as e:
        _log.warning("Nominatim structured falhou: %s", e)
        return None


def _reverse_geocode_nominatim(lat: float, lon: float, timeout: float = 10.0) -> dict | None:
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json", "addressdetails": 1, "zoom": 18},
            headers=_NOMINATIM_HEADERS,
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        addr = data.get("address") or {}
        return {
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "bairro": _bairro_from_nominatim_address(addr),
            "cep": addr.get("postcode"),
            "municipio": addr.get("city") or addr.get("town"),
            "estado": addr.get("state"),
        }
    except requests.RequestException as e:
        _log.warning("Nominatim reverse falhou: %s", e)
        return None


def geocode_with_fallback(
    queries: list[str],
    *,
    endereco: str = "",
    numero: str = "",
    municipio: str = "",
    estado: str = "",
    cep: str = "",
    include_cep_structured: bool = False,
) -> tuple[dict | None, str | None]:
    for query in queries:
        data = _geocode_nominatim_search(query, municipio=municipio, estado=estado)
        if data and (data.get("lat") is not None or data.get("bairro")):
            return data, "nominatim_search"
        time.sleep(1.1)

    for city in _city_names_for_geocode(municipio):
        data = _geocode_nominatim_structured(
            endereco,
            city,
            estado,
            cep if include_cep_structured else "",
            numero=numero,
        )
        if data and (data.get("lat") is not None or data.get("bairro")):
            return data, "nominatim_structured"
        time.sleep(1.1)

    return None, None


def _pending_fields(
    numero: str,
    bairro: str,
    cep: str,
    latitude: Any,
    longitude: Any,
    working_cep: str | None,
) -> list[str]:
    pending: list[str] = []
    if is_invalid_numero(numero):
        pending.append("numero")
    if is_placeholder_or_empty(bairro):
        pending.append("bairro")
    if is_placeholder_or_empty(cep) or not working_cep:
        pending.append("cep")
    if needs_coord_fill(latitude, longitude):
        pending.append("coordenadas")
    return pending


def _build_result_message(
    updates: dict[str, str],
    pending: list[str],
    warnings: list[str],
    sources: list[str],
) -> str:
    unresolved = [f for f in pending if f not in updates]
    if not updates:
        if unresolved:
            msg = f"Não foi possível preencher: {', '.join(unresolved)}."
        else:
            msg = "Nenhum campo vazio ou com placeholder para preencher."
    else:
        msg = f"Atualizado: {', '.join(updates.keys())}."
        if sources:
            msg += f" Fontes: {', '.join(sources)}."
        if unresolved:
            msg += f" Ainda pendente: {', '.join(unresolved)}."
    if warnings:
        msg += " " + " ".join(warnings)
    return msg


def enriquecer_endereco_unidade(payload: dict) -> dict:
    """
    Retorna { success, updates, sources, warnings, message, partial }.
    Só sugere campos vazios ou com placeholder.
    """
    endereco = _clean_str(payload.get("endereco"))
    numero = _clean_str(payload.get("numero"))
    bairro = _clean_str(payload.get("bairro"))
    municipio = _clean_str(payload.get("municipio"))
    estado = _clean_str(payload.get("estado"))
    cep = _clean_str(payload.get("cep"))
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")

    updates: dict[str, str] = {}
    sources: list[str] = []
    warnings: list[str] = []

    working_cep = _normalize_cep_digits(cep)
    need_bairro = is_placeholder_or_empty(bairro)
    need_cep = is_placeholder_or_empty(cep) or not working_cep
    need_coords = needs_coord_fill(latitude, longitude)
    need_numero = is_invalid_numero(numero)

    pending = _pending_fields(numero, bairro, cep, latitude, longitude, working_cep)

    cep_lookup_ok = False
    alta_confianca = False
    cross_meta: dict[str, Any] = {}
    cep_data_ok: dict | None = None

    if need_numero:
        suggested, src = resolve_numero_suggestion(endereco, numero)
        if suggested:
            updates["numero"] = suggested
            numero = suggested
            if src:
                sources.append(src)

    coords = _parse_coords(latitude, longitude)
    cep_bairro_oficial: str | None = None

    cep_digit_candidates = _cep_candidates(cep)
    if cep_digit_candidates or need_bairro or need_cep:
        cep_tried = False
        for cep_try in cep_digit_candidates:
            cep_tried = True
            cep_data, cep_src = fetch_cep_with_fallback(cep_try)
            if cep_data:
                cross_meta = _validate_cep_endereco_cross(cep_data, endereco, municipio, estado)
                if cross_meta.get("city_ok"):
                    cep_lookup_ok = True
                    cep_data_ok = cep_data
                    if f"cep_{cep_src}" not in sources:
                        sources.append(f"cep_{cep_src}")
                    b_cep = _clean_str(cep_data.get("bairro"))
                    if b_cep and not is_placeholder_or_empty(b_cep):
                        cep_bairro_oficial = b_cep
                    alta_confianca = bool(cross_meta.get("high_confidence"))
                    if alta_confianca:
                        sources.append("cep_endereco_validado")
                        if _should_apply_cep_bairro(bairro, b_cep):
                            updates["bairro"] = b_cep
                            bairro = b_cep
                        if need_cep or not _normalize_cep_digits(cep):
                            updates["cep"] = cep_try
                            cep = cep_try
                            working_cep = cep_try
                        loc = cross_meta.get("localidade_cep") or ""
                        uf_cep = _clean_str(cross_meta.get("uf_cep")).upper()[:2]
                        if _should_apply_field_from_cep(municipio, loc, city=True):
                            aliases = _city_aliases_merged()
                            updates["municipio"] = aliases.get(_municipio_lookup_key(loc), loc)
                            municipio = updates["municipio"]
                        if uf_cep and _should_apply_field_from_cep(estado, uf_cep):
                            updates["estado"] = uf_cep
                            estado = uf_cep
                    else:
                        if _should_apply_cep_bairro(bairro, b_cep):
                            updates["bairro"] = b_cep
                            bairro = b_cep
                        if need_cep and not updates.get("cep"):
                            updates["cep"] = cep_try
                            cep = cep_try
                            working_cep = cep_try
                        log_cep = cross_meta.get("logradouro_cep") or ""
                        if log_cep and endereco and cross_meta.get("score", 0) < _LOGRADOURO_MATCH_ALTA:
                            warnings.append(
                                f"Logradouro diverge do CEP (cadastro vs «{log_cep[:50]}», "
                                f"similaridade {cross_meta.get('score', 0):.0%}). Revise endereço ou CEP."
                            )
                    break
                city_api = _clean_str(cep_data.get("localidade") or cep_data.get("city"))
                uf_api = _clean_str(cep_data.get("uf") or cep_data.get("state"))
                msg = (
                    f"CEP {cep_try} pertence a {city_api}/{uf_api}, não a {municipio}/{estado}. "
                    "Busca no mapa usa endereço e município informados."
                )
                if msg not in warnings:
                    warnings.append(msg)
            time.sleep(0.15)
        if cep_tried and need_cep and not updates.get("cep") and (need_bairro and not updates.get("bairro")):
            warnings.append("CEP não encontrado em ViaCEP/OpenCEP/BrasilAPI.")

    if alta_confianca and cep_data_ok and working_cep:
        log_geo = cross_meta.get("logradouro_cep") or endereco
        geo, geo_src = _geocode_alta_confianca(
            log_geo,
            numero,
            municipio,
            estado,
            working_cep,
            cep_bairro_oficial or "",
        )
        if geo and geo.get("lat") is not None and geo.get("lon") is not None:
            new_lat = float(str(geo.get("lat")))
            new_lon = float(str(geo.get("lon")))
            sources.append(f"geo_{geo_src}_cep_validado")
            dist_km = None
            if coords:
                dist_km = _haversine_km(coords[0], coords[1], new_lat, new_lon)
            updates["latitude"] = str(geo.get("lat"))
            updates["longitude"] = str(geo.get("lon"))
            if dist_km is not None and dist_km > 0.4:
                warnings.append(
                    f"Coordenadas ajustadas conforme CEP e logradouro validados "
                    f"(≈{dist_km:.1f} km em relação ao pin anterior)."
                )
        else:
            warnings.append(
                "CEP e endereço validados, mas o mapa não retornou coordenadas para este CEP. "
                "Mantenha ou informe lat/long manualmente."
            )

    elif coords:
        rev = _reverse_geocode_nominatim(coords[0], coords[1])
        time.sleep(1.1)
        if rev:
            rev_bairro = _clean_str(rev.get("bairro"))
            if need_coords and rev.get("lat") is not None and rev.get("lon") is not None:
                updates["latitude"] = str(rev.get("lat"))
                updates["longitude"] = str(rev.get("lon"))
                sources.append("geo_nominatim_reverse")
            elif (
                is_placeholder_or_empty(bairro)
                and not updates.get("bairro")
                and rev_bairro
                and not cep_bairro_oficial
            ):
                updates["bairro"] = rev_bairro
                bairro = rev_bairro
                sources.append("geo_nominatim_reverse")
            elif (
                cep_bairro_oficial
                and rev_bairro
                and not _bairros_equivalent(rev_bairro, cep_bairro_oficial)
                and updates.get("bairro") == cep_bairro_oficial
            ):
                warnings.append(
                    f"Bairro definido pelo CEP ({cep_bairro_oficial}). "
                    f"Coordenadas antigas apontam para {rev_bairro} — use «Completar endereço» com CEP validado."
                )
            if need_cep and not updates.get("cep"):
                rc = _normalize_cep_digits(rev.get("cep"))
                if rc and not cep_lookup_ok:
                    updates["cep"] = rc
                    cep = rc
                    working_cep = rc

    still_need_bairro = is_placeholder_or_empty(bairro) and not updates.get("bairro")
    still_need_cep = (is_placeholder_or_empty(cep) or not _normalize_cep_digits(cep)) and not updates.get("cep")
    still_need_coords = needs_coord_fill(
        updates.get("latitude", latitude),
        updates.get("longitude", longitude),
    )

    if not alta_confianca and (still_need_coords or still_need_bairro or still_need_cep):
        geo_queries = _build_geocode_queries(
            endereco,
            numero,
            municipio,
            estado,
            include_cep=cep_lookup_ok,
            cep=cep,
        )
        if geo_queries:
            geo, geo_src = geocode_with_fallback(
                geo_queries,
                endereco=endereco,
                numero=numero,
                municipio=municipio,
                estado=estado,
                cep=cep,
                include_cep_structured=cep_lookup_ok,
            )
            if geo:
                sources.append(f"geo_{geo_src}")
                if still_need_coords and geo.get("lat") is not None and geo.get("lon") is not None:
                    updates["latitude"] = str(geo.get("lat"))
                    updates["longitude"] = str(geo.get("lon"))
                if still_need_bairro and not updates.get("bairro"):
                    gb = _clean_str(geo.get("bairro"))
                    if gb:
                        updates["bairro"] = gb
                if still_need_cep and not updates.get("cep"):
                    gc = _normalize_cep_digits(geo.get("cep"))
                    if gc:
                        updates["cep"] = gc
            elif still_need_bairro or still_need_coords:
                warnings.append(
                    "Não foi possível localizar no mapa (Nominatim). "
                    "Confira endereço e município; aguarde ~2s entre cliques (limite da API)."
                )
        elif not endereco and not coords:
            warnings.append("Informe o endereço ou coordenadas para buscar dados.")
        elif not geo_queries:
            warnings.append("Dados insuficientes para geocodificação (endereço e município).")

    lat_final = updates.get("latitude", latitude)
    lon_final = updates.get("longitude", longitude)
    cep_final = updates.get("cep", cep)
    pending = _pending_fields(
        updates.get("numero", numero),
        updates.get("bairro", bairro),
        cep_final,
        lat_final,
        lon_final,
        _normalize_cep_digits(cep_final) or working_cep,
    )
    unresolved = [f for f in pending if f not in updates]
    partial = bool(updates) and bool(unresolved)
    updates = _clamp_updates(updates)

    msg = _build_result_message(updates, pending, warnings, sources)
    if alta_confianca and updates:
        msg = f"CEP e endereço validados (alta confiança, {cross_meta.get('score', 0):.0%}). " + msg

    return {
        "success": True,
        "updates": updates,
        "sources": sources,
        "warnings": warnings,
        "partial": partial,
        "pending": unresolved,
        "confidence": "alta" if alta_confianca else ("media" if cep_lookup_ok else "baixa"),
        "logradouro_match_score": cross_meta.get("score"),
        "message": msg,
    }
