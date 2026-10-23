"""Traduz exceção operacional em mensagem para o analista e uma linha de log.

Não devolve SQL, stack, path nem str(e) cru ao cliente.
Não depende do driver MySQL — usa errno e o texto da exceção.

Catálogo (save DMA / CSV e reuso):

- 1062/1169 unique: serial (uq_equipamentos_serial), PRIMARY (duplo envio),
  hostname/id_vgr se o índice existir, demais uniques genéricos
- 1406 campo maior que a coluna
- 1048 NOT NULL
- 1264 valor numérico fora do intervalo (lat/long)
- 1265/3819 ENUM / check (tipo de link, modo)
- 1366 charset
- 1292 valor em formato inválido
- 1451/1452 FK
- 1205/1213 lock/deadlock
- 2003/2006/2013/2055 conexão
- 1054/1146 schema
- OSError/PermissionError arquivo CSV
- demais: fallback com a ação, sem detalhe interno na tela
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from core.utils.fortinet_serial import msg_serial_duplicado_global

_DUP_ENTRY_RE = re.compile(
    r"Duplicate entry ['\"`](.+?)['\"`] for key ['\"`]([^'\"`]+)['\"`]",
    re.IGNORECASE,
)
_DATA_TOO_LONG_RE = re.compile(
    r"Data too long for column ['\"`]([^'\"`]+)['\"`]",
    re.IGNORECASE,
)

_SERIAL_KEY_MARKERS = (
    "uq_equipamentos_serial",
    "idx_serial_equipamentos",
    "serial_equipamentos",
)

_CONN_ERRNOS = frozenset({2003, 2006, 2013, 2055})
_SCHEMA_ERRNOS = frozenset({1054, 1146, 1051, 1142})
_DUP_ERRNOS = frozenset({1062, 1169})
_TOO_LONG_ERRNOS = frozenset({1406})
_NULL_ERRNOS = frozenset({1048})
_RANGE_ERRNOS = frozenset({1264})
_ENUM_ERRNOS = frozenset({1265, 3819})
_CHARSET_ERRNOS = frozenset({1366})
_FORMAT_ERRNOS = frozenset({1292})
_FK_CHILD_ERRNOS = frozenset({1452})
_FK_PARENT_ERRNOS = frozenset({1451})
_LOCK_ERRNOS = frozenset({1205, 1213})

# Colunas do persist DMA/VGR — só rótulo conhecido vai à tela (não vaza schema).
_COL_LABELS = {
    "serial": "Serial",
    "hostname": "Hostname",
    "modelo": "Modelo",
    "endereco": "Endereço",
    "bairro": "Bairro",
    "cidade": "Cidade",
    "uf": "UF",
    "cep": "CEP",
    "nome_unidade": "Nome da unidade",
    "ip_address": "IP",
    "mascara": "Máscara",
    "gateway": "Gateway",
    "subrede": "Subrede",
    "vlan": "VLAN",
    "velocidade": "Velocidade",
    "operadora": "Operadora",
    "designador": "Designador",
    "identificador": "Identificador",
    "id_vgr": "ID VGR",
    "id_vgr_link": "ID VGR do link",
    "codigo": "Licença",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "pppoe_user": "Usuário PPPoE",
}

_LEAK_MARKERS = (
    "select ",
    "insert ",
    "update ",
    "delete ",
    "traceback",
    "file \"",
    "<script",
    "mysql",
    "errno",
)


@dataclass(frozen=True)
class DbErrorInfo:
    user_message: str
    log_message: str


def _one_line(text: Any, *, limit: int = 180) -> str:
    s = " ".join(str(text or "").strip().split())
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _safe_display_value(value: Any, *, limit: int = 64) -> str:
    s = re.sub(r"[<>\"'`]", "", str(value or ""))
    s = " ".join(s.split())
    if len(s) > limit:
        return s[: limit - 1] + "…"
    return s


def _errno(exc: BaseException) -> int | None:
    raw = getattr(exc, "errno", None)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _key_basename(key_name: str) -> str:
    raw = (key_name or "").strip()
    if "." in raw:
        return raw.rsplit(".", 1)[-1]
    return raw


def _is_serial_key(key_name: str) -> bool:
    base = _key_basename(key_name).lower()
    full = (key_name or "").lower()
    if any(m in base or m in full for m in _SERIAL_KEY_MARKERS):
        return True
    return "serial" in base


def _user_leaks_internal(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _LEAK_MARKERS)


def _info(ctx: str, user: str, *, detalhe: str | None = None) -> DbErrorInfo:
    user = " ".join((user or "").split())
    if _user_leaks_internal(user):
        user = "Não foi possível concluir a operação. Tente novamente."
    log_msg = f"{ctx}: {user}"
    if detalhe:
        log_msg = f"{log_msg} ({_one_line(detalhe)})"
    return DbErrorInfo(user, log_msg)


def explain_db_error(
    exc: BaseException,
    *,
    contexto: str,
    acao: str = "concluir a operação",
) -> DbErrorInfo:
    """Mensagem objetiva para flash/API e a mesma causa em uma linha de log."""
    errno = _errno(exc)
    tipo = type(exc).__name__
    raw = _one_line(exc)
    ctx = (contexto or "operacao").strip() or "operacao"
    acao_txt = (acao or "concluir a operação").strip()
    detalhe = f"{tipo} errno={errno} {raw}"

    if isinstance(exc, (FileNotFoundError, PermissionError)) or (
        isinstance(exc, OSError)
        and getattr(exc, "filename", None)
        and not isinstance(exc, ConnectionError)
    ):
        return _info(
            ctx,
            "Não foi possível gravar o arquivo CSV. Tente novamente.",
            detalhe=detalhe,
        )

    dup = _DUP_ENTRY_RE.search(str(exc))
    if errno in _DUP_ERRNOS or dup:
        value = _safe_display_value(dup.group(1) if dup else "")
        key = dup.group(2) if dup else ""
        base = _key_basename(key).lower()
        if _is_serial_key(key):
            user = msg_serial_duplicado_global(value)
            return _info(ctx, user)
        if base == "primary":
            return _info(
                ctx,
                "Conflito ao salvar (possível duplo clique). "
                "Atualize a tela e confira se o registro já foi gravado.",
                detalhe=detalhe,
            )
        if "hostname" in base:
            return _info(
                ctx,
                "Este hostname já está cadastrado em outro equipamento.",
                detalhe=detalhe,
            )
        if "id_vgr" in base:
            return _info(
                ctx,
                "Este ID VGR já está cadastrado em outro registro.",
                detalhe=detalhe,
            )
        return _info(
            ctx,
            "Já existe um cadastro com esse valor. "
            "Corrija o campo duplicado e tente de novo.",
            detalhe=f"{detalhe} chave={base} valor={value}",
        )

    too_long = _DATA_TOO_LONG_RE.search(str(exc))
    if errno in _TOO_LONG_ERRNOS or too_long:
        col = (too_long.group(1) if too_long else "").strip()
        label = _COL_LABELS.get(col.lower())
        if label:
            user = (
                f"O campo «{label}» excede o tamanho permitido. "
                "Encurte o valor e tente de novo."
            )
        else:
            user = (
                "Um dos campos excede o tamanho permitido. "
                "Confira os valores e tente de novo."
            )
        extra = f" coluna={col}" if col else ""
        return _info(ctx, user, detalhe=f"{tipo} errno={errno or 1406}{extra}")

    if errno in _NULL_ERRNOS:
        return _info(
            ctx,
            "Um campo obrigatório ficou vazio ao gravar. "
            "Confira o formulário e tente de novo.",
            detalhe=detalhe,
        )

    if errno in _RANGE_ERRNOS:
        return _info(
            ctx,
            "Latitude ou longitude está fora do intervalo permitido.",
            detalhe=detalhe,
        )

    if errno in _ENUM_ERRNOS:
        return _info(
            ctx,
            "Um valor da lista fechada é inválido (tipo de link ou modo de conexão). "
            "Recarregue a página e selecione uma opção válida.",
            detalhe=detalhe,
        )

    if errno in _CHARSET_ERRNOS:
        return _info(
            ctx,
            "Há caracteres não suportados em algum campo. "
            "Remova símbolos especiais e tente de novo.",
            detalhe=detalhe,
        )

    if errno in _FORMAT_ERRNOS:
        return _info(
            ctx,
            "Um valor está em formato inválido para gravar. "
            "Confira os campos e tente de novo.",
            detalhe=detalhe,
        )

    if errno in _FK_CHILD_ERRNOS:
        return _info(
            ctx,
            "Não foi possível gravar: referência inválida de unidade ou equipamento.",
            detalhe=detalhe,
        )

    if errno in _FK_PARENT_ERRNOS:
        return _info(
            ctx,
            "Não foi possível alterar este registro porque outros cadastros dependem dele.",
            detalhe=detalhe,
        )

    if errno in _LOCK_ERRNOS:
        return _info(
            ctx,
            "O banco está ocupado. Aguarde alguns segundos e tente novamente.",
            detalhe=detalhe,
        )

    if errno in _CONN_ERRNOS or "can't connect" in raw.lower() or "lost connection" in raw.lower():
        return _info(
            ctx,
            "Não foi possível gravar agora. Tente novamente em instantes.",
            detalhe=detalhe,
        )

    if (
        errno in _SCHEMA_ERRNOS
        or "unknown column" in raw.lower()
        or "doesn't exist" in raw.lower()
    ):
        return _info(
            ctx,
            "Cadastro temporariamente indisponível (estrutura do banco). Tente mais tarde.",
            detalhe=detalhe,
        )

    return _info(
        ctx,
        f"Não foi possível {acao_txt}. Tente novamente.",
        detalhe=detalhe,
    )
