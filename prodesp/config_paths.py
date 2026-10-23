"""
Caminhos externos do módulo PRODESP — lidos de config.ini (gerado pelo .bat de produção)
ou PRODESP_CADERNO_NETWORK_DIR no .env.

Caderno de teste (.xlsm): cópia local em static/caderno_teste/gerados/ + rede em
  {caderno_teste_rede_base}/{acronimo_unidades}/arquivo.xlsm

Duas raízes (bibliotecas com nomes diferentes — não unificar):
  principal: C:\\Users\\{user}\\Telefonica\\Projeto_Prodesp.TMBNL - Documentos\\
  fallback:  C:\\Users\\{user}\\OneDrive - Telefonica\\Documentos - Projeto_Prodesp.TMBNL\\
"""
from __future__ import annotations

import configparser
import os
import re

PRODESP_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG_INI_PATH = os.path.join(PRODESP_DIR, "config.ini")

_CADERNO_SUBPATH = r"Rollout - Prodesp\Caderno de Testes"
_CERTIFICADOS_SUBPATH = r"Rollout - Prodesp\Certificados"
_PRODESP_DOCS_PRINCIPAL = r"Projeto_Prodesp.TMBNL - Documentos"
_PRODESP_DOCS_FALLBACK = r"Documentos - Projeto_Prodesp.TMBNL"

_ENV_PRIMARY = {
    "caderno_teste_rede_base": "PRODESP_CADERNO_NETWORK_DIR",
    "certificados_rede_base": "PRODESP_CERTIFICADO_NETWORK_DIR",
}
_ENV_FALLBACK = {
    "caderno_teste_rede_base": "PRODESP_CADERNO_NETWORK_DIR_FALLBACK",
    "certificados_rede_base": "PRODESP_CERTIFICADO_NETWORK_DIR_FALLBACK",
}


def _windows_user() -> str:
    return (os.environ.get("USERNAME") or os.environ.get("USER") or "").strip()


def _principal_root() -> str:
    return os.path.join(rf"C:\Users\{_windows_user()}", "Telefonica")


def _fallback_root() -> str:
    return os.path.join(rf"C:\Users\{_windows_user()}", "OneDrive - Telefonica")


def _default_path_candidates(key: str) -> tuple[str, str]:
    principal = _principal_root()
    fallback = _fallback_root()
    if key == "caderno_teste_rede_base":
        return (
            os.path.join(principal, _PRODESP_DOCS_PRINCIPAL, _CADERNO_SUBPATH),
            os.path.join(fallback, _PRODESP_DOCS_FALLBACK, _CADERNO_SUBPATH),
        )
    if key == "certificados_rede_base":
        return (
            os.path.join(principal, _PRODESP_DOCS_PRINCIPAL, _CERTIFICADOS_SUBPATH),
            os.path.join(fallback, _PRODESP_DOCS_FALLBACK, _CERTIFICADOS_SUBPATH),
        )
    return ("", "")


def _default_paths() -> dict[str, str]:
    """Primeiro candidato (principal) — compatível com chamadas antigas."""
    cad_p, cad_f = _default_path_candidates("caderno_teste_rede_base")
    cert_p, cert_f = _default_path_candidates("certificados_rede_base")
    del cad_f, cert_f
    return {
        "caderno_teste_rede_base": cad_p,
        "certificados_rede_base": cert_p,
    }


def _ini_get(key: str) -> str:
    if not os.path.isfile(CONFIG_INI_PATH):
        return ""
    config = configparser.ConfigParser()
    config.read(CONFIG_INI_PATH, encoding="utf-8")
    try:
        return config.get("Paths", key, fallback="").strip()
    except (configparser.NoSectionError, configparser.NoOptionError):
        return ""


def _unique_paths(*paths: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in paths:
        value = (raw or "").strip()
        if not value:
            continue
        token = os.path.normcase(os.path.abspath(value))
        if token in seen:
            continue
        seen.add(token)
        out.append(value)
    return out


def network_base_ready(base: str) -> bool:
    """True se a pasta já existe ou um ancestral permite criar subpastas sem inventar a raiz de sync."""
    if not (base or "").strip():
        return False
    current = os.path.abspath(base)
    if os.path.isdir(current):
        return True
    while True:
        parent = os.path.dirname(current)
        if parent == current:
            return False
        parent_name = os.path.basename(parent).lower()
        if parent_name in ("telefonica", "onedrive - telefonica"):
            return os.path.isdir(current)
        if os.path.isdir(parent):
            return True
        current = parent


def list_prodesp_path_candidates(key: str) -> list[str]:
    """Principal e fallback (ini do .bat → default do código; env só se o ini não definir)."""
    ini_primary = _ini_get(key)
    ini_fallback = _ini_get(f"{key}_fallback")
    env_primary = (os.environ.get(_ENV_PRIMARY.get(key, "")) or "").strip()
    env_fallback = (os.environ.get(_ENV_FALLBACK.get(key, "")) or "").strip()
    code_primary, code_fallback = _default_path_candidates(key)
    if ini_primary or ini_fallback:
        return _unique_paths(
            ini_primary or code_primary,
            ini_fallback or code_fallback,
        )
    return _unique_paths(code_primary, env_primary, env_fallback, code_fallback)


def load_prodesp_path(key: str, default: str | None = None) -> str:
    """Retorna o primeiro caminho utilizável (principal, senão fallback)."""
    candidates = list_prodesp_path_candidates(key)
    if default:
        candidates = _unique_paths(default, *candidates)
    for path in candidates:
        if network_base_ready(path) or os.path.isdir(path) or os.path.isfile(path):
            return path
    if candidates:
        return candidates[0]
    return ""


def sanitize_pasta_acronimo(acronimo: str, *, max_len: int = 80) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (acronimo or "").strip())
    s = re.sub(r"\s+", " ", s).strip("._ ")
    if len(s) > max_len:
        s = s[:max_len].rstrip("._ ")
    return s


def iter_pastas_rede_caderno(acronimo: str, *, base_override: str = ""):
    """Pastas {base}/{acronimo}/ na ordem principal → fallback."""
    acr = sanitize_pasta_acronimo(acronimo) or "_sem_acronimo"
    if (base_override or "").strip():
        yield os.path.join(base_override.strip(), acr)
        return
    for base in list_prodesp_path_candidates("caderno_teste_rede_base"):
        yield os.path.join(base, acr)


def resolve_pasta_rede_caderno(acronimo: str, *, base_override: str = "") -> str:
    """
    Primeira pasta de destino na rede: {base}/{acronimo}/.
    Para gravar com fallback use iter_pastas_rede_caderno.
    """
    for pasta in iter_pastas_rede_caderno(acronimo, base_override=base_override):
        return pasta
    return ""


def _parse_acronimo_dir_map(env_name: str) -> dict[str, str]:
    """
    Mapa acrônimo → pasta base.
    Formato .env: DER=C:\\Certificados\\DER;POUPATEMPO=C:\\Certificados\\PT
    (vírgula, ponto-e-vírgula ou quebra de linha entre entradas).
    """
    raw = (os.environ.get(env_name) or "").strip()
    result: dict[str, str] = {}
    if not raw:
        return result
    for part in re.split(r"[;\n]+", raw):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, path = chunk.partition("=")
        acr = sanitize_pasta_acronimo(key).upper()
        dest = path.strip().strip('"').strip("'")
        if acr and dest:
            result[acr] = os.path.abspath(dest)
    return result


def _certificados_dir_map_from_ini(kind: str) -> dict[str, str]:
    """
    [Paths] no config.ini — chaves certificados_rede_base_DER, certificados_local_base_POUPATEMPO, etc.
    """
    prefix = f"certificados_{kind}_base_"
    result: dict[str, str] = {}
    config = configparser.ConfigParser()
    if not os.path.isfile(CONFIG_INI_PATH):
        return result
    config.read(CONFIG_INI_PATH, encoding="utf-8")
    try:
        for key, value in config.items("Paths"):
            low = key.lower()
            if not low.startswith(prefix):
                continue
            # Não tratar certificados_rede_base_fallback como acrônimo.
            suffix = key[len(prefix) :]
            if suffix.lower() == "fallback":
                continue
            acr = sanitize_pasta_acronimo(suffix).upper()
            dest = (value or "").strip()
            if acr and dest:
                result[acr] = os.path.abspath(dest)
    except (configparser.NoSectionError, configparser.NoOptionError):
        pass
    return result


def _certificados_dir_map(kind: str) -> dict[str, str]:
    """kind: rede | local — ini primeiro, .env sobrescreve."""
    merged = _certificados_dir_map_from_ini(kind)
    env_name = (
        "PRODESP_CERTIFICADO_NETWORK_DIRS"
        if kind == "rede"
        else "PRODESP_CERTIFICADO_LOCAL_DIRS"
    )
    merged.update(_parse_acronimo_dir_map(env_name))
    return merged


def resolve_certificados_rede_base(acronimo: str = "") -> str:
    """
    Pasta base na rede/OneDrive para certificados.
    Com mapeamento por acrônimo, retorna a raiz específica (ex.: DER).
    Sem mapeamento, usa o primeiro candidato de certificados_rede_base.
    """
    acr = sanitize_pasta_acronimo(acronimo).upper()
    if acr:
        mapped = _certificados_dir_map("rede")
        if acr in mapped:
            return mapped[acr]
    return (load_prodesp_path("certificados_rede_base") or "").strip()


def iter_certificados_rede_bases(acronimo: str = "") -> list[str]:
    """Bases de certificado na rede: mapeamento por acrônimo ou principal + fallback."""
    acr = sanitize_pasta_acronimo(acronimo).upper()
    if acr:
        mapped = _certificados_dir_map("rede")
        if acr in mapped:
            return [mapped[acr]]
    return list_prodesp_path_candidates("certificados_rede_base")


def resolve_certificados_local_base() -> str:
    """
    Pasta raiz interna do Portal (fora de static/ — não exposta em /prodesp/static/...).
    Default: prodesp/var/certificados/ ou PRODESP_CERTIFICADO_LOCAL_DIR.
    """
    env = (os.environ.get("PRODESP_CERTIFICADO_LOCAL_DIR") or "").strip()
    if env:
        return os.path.abspath(env)
    return os.path.join(PRODESP_DIR, "var", "certificados")


def resolve_certificados_local_base_for(acronimo: str = "") -> str:
    """Pasta base interna do Portal; suporta override por acrônimo."""
    acr = sanitize_pasta_acronimo(acronimo).upper()
    if acr:
        mapped = _certificados_dir_map("local")
        if acr in mapped:
            return mapped[acr]
    return resolve_certificados_local_base()


def iter_pastas_certificado(acronimo: str, hostname: str, *, rede: bool = False) -> list[str]:
    """Destinos do certificado: mapeamento por acrônimo ou principal + fallback."""
    acr = sanitize_pasta_acronimo(acronimo) or "_sem_acronimo"
    host = sanitize_pasta_acronimo(hostname) or "_sem_hostname"
    if not rede:
        base = resolve_certificados_local_base_for(acronimo)
        mapped = _certificados_dir_map("local")
        if acr.upper() in mapped:
            return [os.path.join(base, host)]
        return [os.path.join(base, acr, host)]
    mapped = _certificados_dir_map("rede")
    if acr.upper() in mapped:
        return [os.path.join(mapped[acr.upper()], host)]
    out: list[str] = []
    for base in iter_certificados_rede_bases(acronimo):
        if base:
            out.append(os.path.join(base, acr, host))
    return out


def resolve_pasta_certificado(acronimo: str, hostname: str, *, rede: bool = False) -> str:
    """
    Destino do certificado por unidade (primeiro candidato).

    Padrão: {base}/{acronimo}/{hostname}/
    Com mapeamento (PRODESP_CERTIFICADO_*_DIRS ou config.ini): {pasta_do_acronimo}/{hostname}/
    """
    pastas = iter_pastas_certificado(acronimo, hostname, rede=rede)
    return pastas[0] if pastas else ""
