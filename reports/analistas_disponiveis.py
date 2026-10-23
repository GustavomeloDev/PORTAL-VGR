"""Analistas IMPLANTAÇÃO livres (sem atendimento em andamento), com blacklist por nome/e-mail."""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from login.portal_access_config import DEPT_IMPLANTACAO


@dataclass(frozen=True)
class AnalistaDisponivel:
    nome: str
    email: str = ""
    status: str = ""
    na_plataforma: bool = False
    finalizados: int = 0

    @property
    def status_label(self) -> str:
        return (self.status or "").strip() or "—"

    @property
    def plataforma_label(self) -> str:
        return "Ativo" if self.na_plataforma else "Inativo"


def _norm(texto: str) -> str:
    raw = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in raw if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def token_na_blacklist(nome: str, email: str, tokens: Iterable[str]) -> bool:
    nome_n = _norm(nome)
    email_n = _norm(email)
    if not nome_n and not email_n:
        return False
    for raw in tokens:
        token = _norm(raw)
        if not token:
            continue
        if token == nome_n or token == email_n:
            return True
        if "@" in token and token == email_n:
            return True
        if " " in token and token in nome_n:
            return True
    return False


def _stats_por_nome(nome: str, contagens: Mapping[str, Mapping[str, Any]]) -> Mapping[str, Any]:
    stats = contagens.get(nome) or contagens.get(nome.casefold()) or {}
    if stats:
        return stats
    chave = _norm(nome)
    for knome, kval in contagens.items():
        if _norm(str(knome)) == chave:
            return kval
    return {}


def usuario_desabilitado(row: Mapping[str, Any]) -> bool:
    return _flag_ligada(row.get("usuario_desabilitado_user"))


def usuario_admin(row: Mapping[str, Any]) -> bool:
    return _flag_ligada(row.get("admin_user"))


def _flag_ligada(raw: Any) -> bool:
    if raw is None:
        return False
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "ignore")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return int(raw) != 0
    s = str(raw).strip().lower()
    return s not in ("", "0", "false", "nao", "não", "no", "off")


def _online(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    return str(val or "").strip().lower() in ("1", "true", "sim", "ativo")


def filtrar_analistas_disponiveis(
    usuarios: Sequence[Mapping[str, object]],
    contagens: Mapping[str, Mapping[str, object]],
    blacklist: Sequence[str],
    *,
    dept_principal: str = DEPT_IMPLANTACAO,
) -> list[AnalistaDisponivel]:
    """Principal IMPLANTAÇÃO, ativo no cadastro, sem atendimento em andamento, fora da blacklist."""
    saida: list[AnalistaDisponivel] = []
    vistos: set[str] = set()
    for row in usuarios:
        if usuario_desabilitado(row):
            continue
        if usuario_admin(row):
            continue
        dept = str(row.get("departamento_user") or "").strip()
        if dept != dept_principal:
            continue
        nome = str(row.get("nome_user") or "").strip()
        email = str(row.get("email_user") or "").strip()
        if not nome:
            continue
        chave = _norm(nome)
        if chave in vistos:
            continue
        if token_na_blacklist(nome, email, blacklist):
            continue
        stats = _stats_por_nome(nome, contagens)
        if int(stats.get("em_andamento") or 0) != 0:
            continue
        vistos.add(chave)
        saida.append(
            AnalistaDisponivel(
                nome=nome,
                email=email,
                status=str(row.get("nome_status_disponibilidade") or "").strip(),
                na_plataforma=_online(row.get("is_online")),
                finalizados=int(stats.get("finalizado") or 0),
            )
        )
    saida.sort(key=lambda a: _norm(a.nome))
    return saida


def ordenar_analistas_destaque(analistas: Sequence[AnalistaDisponivel]) -> list[AnalistaDisponivel]:
    """Ativo na plataforma e Disponível primeiro — recorte do Teams cabe nesses."""

    def chave(a: AnalistaDisponivel) -> tuple:
        disp = "dispon" in (a.status_label or "").casefold()
        return (0 if a.na_plataforma else 1, 0 if disp else 1, _norm(a.nome))

    return sorted(analistas, key=chave)
