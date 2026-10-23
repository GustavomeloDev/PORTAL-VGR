"""Carimbo NOC genérico (texto) a partir de um contexto tipado pelo módulo."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

_RE_VER_CURTA = re.compile(r"v?(\d+\.\d+(?:\.\d+)?)", re.I)


def frase_admin_carimbo(resumo: str) -> str:
    """Uma linha no carimbo, alinhada ao texto da coleta PRODESP."""
    low = (resumo or "").lower()
    if not low.strip():
        return "Limpeza do usuário admin: não executada"
    if "não cadastrado" in low or "nao cadastrado" in low:
        return "Usuário admin não cadastrado"
    if "ainda aparece" in low or "ainda listado" in low:
        return "Falha ao remover usuário admin"
    if "falha" in low and "admin" in low:
        return "Falha ao remover usuário admin"
    if "não consta mais" in low or "nao consta mais" in low:
        return "Usuário admin deletado"
    if "remoção: ok" in low or "remocao: ok" in low:
        return "Usuário admin deletado"
    return "Usuário admin deletado"


def firmware_carimbo(version_raw: str) -> str:
    text = (version_raw or "").strip()
    if not text:
        return ""
    m = _RE_VER_CURTA.search(text)
    ver = m.group(1) if m else text.split(",", 1)[0].strip()
    if ver.lower().startswith("v"):
        ver = ver[1:]
    return f"Firmware atualizado para {ver}"


def formatar_velocidade_carimbo(velocidade: str) -> str:
    """«400» / «400 Mbps» → «400MB» (modelo NOC DMA)."""
    raw = (velocidade or "").strip()
    if not raw:
        return ""
    if re.search(r"(?i)mb", raw):
        num = re.sub(r"(?i)\s*m(?:bps|b)\s*$", "", raw).strip()
        return f"{num}MB" if num else raw
    m = re.match(r"^(\d+(?:[.,]\d+)?)\s*$", raw)
    if m:
        return f"{m.group(1).replace(',', '.')}MB"
    return raw


def _linha(rotulo: str, valor: Any) -> str:
    v = "" if valor is None else str(valor).strip()
    if not v:
        return ""
    if rotulo:
        return f"{rotulo}: {v}"
    return v


def montar_bloco_link(
    *,
    ordem: int,
    operadora: str,
    velocidade: str,
    designador: str,
    id_vgr_link: str,
    ip_wan: str,
    telefone_reparo: str,
    topologia: str,
    tipo: str,
    solucao: str,
    fornecedor: str,
    modelo: str,
    serial: str,
    possui_projeto_tecnico: str = "Sim",
) -> str:
    titulo = f"LINK {ordem} - IP DEDICADO: {(operadora or '').strip().upper() or 'N/A'}"
    linhas = [
        titulo,
        _linha("Velocidade", velocidade),
        _linha("LP/DESIGNADOR", designador),
        _linha("IPD", id_vgr_link),
        _linha("IP DE WAN", ip_wan),
        _linha("Tel de Reparo", telefone_reparo),
        _linha("Topologia", topologia),
        _linha("Tipo", tipo),
        _linha("Solução", solucao),
        _linha("Fornecedor", fornecedor),
        _linha("Modelo", modelo),
        _linha("Serial", serial),
        _linha("Possui Projeto Técnico", possui_projeto_tecnico),
    ]
    return "\n".join(x for x in linhas if x).strip()


def montar_carimbo_noc(
    *,
    loopback: str,
    frase_admin: str,
    firmware: str,
    licenca_forticloud: str,
    fortimanager: str,
    id_vgr: str,
    topologia: str,
    solucao: str,
    fornecedor: str,
    modelo: str,
    chave_licenca: str,
    serial: str,
    links: Sequence[Mapping[str, Any]] | None = None,
    logs_texto: str = "",
) -> str:
    """Cabeçalho + links + logs (modelo DMA/NOC). Campos vazios são omitidos."""
    cabeca = [
        _linha("Loopback", loopback),
        (frase_admin or "").strip(),
        (firmware or "").strip(),
        (licenca_forticloud or "").strip(),
        (fortimanager or "").strip(),
        _linha("ID VGR", id_vgr),
        _linha("TOPOLOGIA", topologia),
        _linha("SOLUÇÃO", solucao),
        _linha("FORNECEDOR", fornecedor),
        _linha("MODELO EQUIPAMENTO", modelo),
        _linha("CHAVE DE LICENÇA", chave_licenca),
        _linha("SERIAL NUMBER EQTO", serial),
    ]
    partes = ["\n".join(x for x in cabeca if x).strip()]
    for idx, link in enumerate(links or [], start=1):
        bloco = montar_bloco_link(
            ordem=int(link.get("ordem") or idx),
            operadora=str(link.get("operadora") or ""),
            velocidade=formatar_velocidade_carimbo(str(link.get("velocidade") or "")),
            designador=str(link.get("designador") or ""),
            id_vgr_link=str(link.get("id_vgr_link") or link.get("ipd") or ""),
            ip_wan=str(link.get("ip_wan") or link.get("ip_address") or ""),
            telefone_reparo=str(link.get("telefone_reparo") or ""),
            topologia=str(link.get("topologia") or ""),
            tipo=str(link.get("tipo") or ""),
            solucao=str(link.get("solucao") or solucao),
            fornecedor=str(link.get("fornecedor") or fornecedor),
            modelo=str(link.get("modelo") or modelo),
            serial=str(link.get("serial") or serial),
            possui_projeto_tecnico=str(link.get("possui_projeto_tecnico") or "Sim"),
        )
        if bloco:
            partes.append(bloco)
    logs = (logs_texto or "").strip()
    if logs:
        partes.append(logs)
    return "\n\n".join(p for p in partes if p).strip()
