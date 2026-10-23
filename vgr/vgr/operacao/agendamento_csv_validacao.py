"""
Validação de linhas do CSV de agendamento VGR (portal + testes).

Espelha ``prodesp/prodesp/agendamento_csv_validacao.py``. Diferenças VGR:
  - coluna extra ``tipo_servico`` (equipamentos.tipo_servico: SDWAN|SDWIFI|SDLAN);
  - ID VGR é o de ``equipamentos.id_vgr`` (texto até 64, não só dígitos);
  - contratadas vêm da tabela ``contratadas`` (lista dinâmica, não fixa no código);
  - Field até 128 caracteres (``fields.nome``).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Iterable

TIPOS_SERVICO_CSV: tuple[str, ...] = ("SDWAN", "SDWIFI", "SDLAN")

# Contratadas aceitas no CSV de agendamento (regra de negócio fixa).
# O valor gravado/exibido é o nome canônico desta tupla; o casamento com o que
# veio no CSV (e com o cadastro em `contratadas`) ignora maiúsculas, acentos,
# espaços e pontuação: "VIVO REDES", "vivo-redes", "VivoRedes" → "Vivo Redes";
# "MAMINFO" → "MAMInfo".
CONTRATADAS_CSV_PERMITIDAS: tuple[str, ...] = (
    "DELFIA",
    "MAMInfo",
    "SPREAD",
    "INELCOM",
    "Vivo Redes",
)

MSG_DUPLICATA_VGR = (
    "ID VGR + tipo de serviço duplicado no arquivo "
    "(segunda ocorrência ignorada; mantida a primeira)."
)
MSG_UNIDADE_REPETIDA = (
    "Unidade já processada neste arquivo (outro ID VGR/serviço da mesma unidade)."
)

_CSV_PLACEHOLDERS_VAZIOS = frozenset({
    "",
    "-",
    "—",
    "–",
    "n/a",
    "na",
    "null",
    "none",
    "sem",
    "s/n",
})

ID_VGR_MAX_CHARS = 64
FIELD_MAX_CHARS = 128
CONTATO_MIN_DIGITS = 10
CONTATO_MAX_DIGITS = 11

_ID_VGR_RE = re.compile(r"^[A-Za-z0-9._/\-]+$")
_HORA_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")


def csv_valor_ausente(val) -> bool:
    if val is None:
        return True
    s = str(val).strip().lower()
    return not s or s in _CSV_PLACEHOLDERS_VAZIOS


def normalizar_contato_field(val) -> str | None:
    if val is None:
        return None
    digits = "".join(c for c in str(val) if c.isdigit())
    return digits[:20] if digits else None


def normalizar_hora_csv(val) -> str | None:
    """'9:5' inválido; '09:30' / '9:30' / '09:30:00' → '09:30:00'. None se inválida."""
    if csv_valor_ausente(val):
        return None
    m = _HORA_RE.match(str(val).strip())
    if not m:
        return None
    hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def validar_id_vgr_csv(id_vgr) -> str | None:
    s = str(id_vgr or "").strip()
    if not s:
        return "ID VGR obrigatório."
    if len(s) > ID_VGR_MAX_CHARS:
        return f"ID VGR excede {ID_VGR_MAX_CHARS} caracteres."
    if not _ID_VGR_RE.match(s):
        return f"ID VGR inválido ({s}). Use letras, números, '.', '-', '_' ou '/' (sem espaços)."
    return None


def normalizar_tipo_servico_csv(val) -> tuple[str | None, str | None]:
    """Retorna (tipo_canonico, erro)."""
    if csv_valor_ausente(val):
        lista = ", ".join(TIPOS_SERVICO_CSV)
        return None, f"Tipo de serviço obrigatório. Valores permitidos: {lista}"
    bruto = str(val).strip().upper().replace("-", "").replace(" ", "")
    if bruto in TIPOS_SERVICO_CSV:
        return bruto, None
    lista = ", ".join(TIPOS_SERVICO_CSV)
    return None, f"Tipo de serviço inválido ({str(val).strip()}). Valores permitidos: {lista}"


def chave_contratada(val) -> str:
    """Chave de comparação: sem acento, minúscula, só [a-z0-9]."""
    s = unicodedata.normalize("NFKD", str(val or ""))
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", s)


def canonical_contratada(
    val, permitidas: Iterable[str] = CONTRATADAS_CSV_PERMITIDAS
) -> str | None:
    chave = chave_contratada(val)
    if not chave:
        return None
    for nome in permitidas:
        if chave_contratada(nome) == chave:
            return str(nome).strip()
    return None


def validar_contratada_planejada(
    val, permitidas: Iterable[str] = CONTRATADAS_CSV_PERMITIDAS
) -> tuple[str | None, str | None]:
    if csv_valor_ausente(val):
        return None, None
    lista_ok = list(permitidas)
    canon = canonical_contratada(val, lista_ok)
    if canon:
        return canon, None
    lista = ", ".join(lista_ok) or "(nenhuma contratada configurada)"
    return None, f"Contratada inválida ({str(val).strip()}). Valores permitidos: {lista}"


def validar_data_agendamento_csv(data_agendamento, *, obrigatoria: bool = False) -> str | None:
    if not data_agendamento:
        return "Data de agendamento obrigatória." if obrigatoria else None
    bruto = str(data_agendamento).strip()
    try:
        datetime.strptime(bruto[:10], "%Y-%m-%d").date()
    except ValueError:
        return f"Data inválida ({bruto}). Use dd/mm/yyyy."
    return None


def validar_field_contato_csv(field_planejado, contato_field) -> tuple[str | None, str | None]:
    if csv_valor_ausente(field_planejado):
        return None, None
    if len(str(field_planejado).strip()) > FIELD_MAX_CHARS:
        return f"Field excede {FIELD_MAX_CHARS} caracteres.", None
    contato_norm = normalizar_contato_field(contato_field)
    if (
        not contato_norm
        or len(contato_norm) < CONTATO_MIN_DIGITS
        or len(contato_norm) > CONTATO_MAX_DIGITS
    ):
        return "Contato Field obrigatório (10 ou 11 dígitos) quando Field está preenchido.", None
    return None, contato_norm


def validar_field_contratada_csv(
    contratada_canonica: str | None,
    field_planejado,
    permitidas: Iterable[str] = CONTRATADAS_CSV_PERMITIDAS,
) -> str | None:
    if csv_valor_ausente(field_planejado) or not contratada_canonica:
        return None
    field_canon = canonical_contratada(field_planejado, permitidas)
    if field_canon and field_canon != contratada_canonica:
        return (
            f"Field ({field_canon}) não corresponde à contratada ({contratada_canonica}). "
            "Quando Field é uma empresa da lista de contratadas, deve ser igual à contratada."
        )
    return None


def validar_agendamento_csv_linha(
    *,
    id_vgr,
    tipo_servico,
    data_agendamento,
    hora_agendamento,
    contratada,
    field_planejado=None,
    contato_field=None,
    tem_agenda: bool,
    contratadas_permitidas: Iterable[str] = CONTRATADAS_CSV_PERMITIDAS,
) -> tuple[str | None, dict]:
    """
    Retorna (erro, normalizados) — normalizados contém:
    tipo_servico, hora_norm, contratada_canonica, contato_norm.
    """
    permitidas = list(contratadas_permitidas)
    norm: dict = {
        "tipo_servico": None,
        "hora_norm": None,
        "contratada_canonica": None,
        "contato_norm": None,
    }

    err = validar_id_vgr_csv(id_vgr)
    if err:
        return err, norm

    tipo, err = normalizar_tipo_servico_csv(tipo_servico)
    if err:
        return err, norm
    norm["tipo_servico"] = tipo

    if tem_agenda:
        err = validar_data_agendamento_csv(data_agendamento, obrigatoria=True)
        if err:
            return err, norm
        if csv_valor_ausente(hora_agendamento):
            return "Hora de agendamento obrigatória.", norm
        norm["hora_norm"] = normalizar_hora_csv(hora_agendamento)
        if not norm["hora_norm"]:
            return f"Hora inválida ({str(hora_agendamento).strip()}). Use o formato HH:mm.", norm
        if csv_valor_ausente(contratada):
            lista = ", ".join(permitidas) or "(nenhuma contratada configurada)"
            return f"Contratada obrigatória para agendamento. Valores permitidos: {lista}", norm
        norm["contratada_canonica"], err = validar_contratada_planejada(contratada, permitidas)
        if err:
            return err, norm
    else:
        if data_agendamento:
            err = validar_data_agendamento_csv(data_agendamento)
            if err:
                return err, norm
        if not csv_valor_ausente(contratada):
            norm["contratada_canonica"], err = validar_contratada_planejada(contratada, permitidas)
            if err:
                return err, norm
        if not csv_valor_ausente(hora_agendamento):
            norm["hora_norm"] = normalizar_hora_csv(hora_agendamento)
            if not norm["hora_norm"]:
                return (
                    f"Hora inválida ({str(hora_agendamento).strip()}). Use o formato HH:mm.",
                    norm,
                )

    err, contato_norm = validar_field_contato_csv(field_planejado, contato_field)
    if err:
        return err, norm
    norm["contato_norm"] = contato_norm

    err = validar_field_contratada_csv(norm["contratada_canonica"], field_planejado, permitidas)
    if err:
        return err, norm

    if contato_norm is None and not csv_valor_ausente(contato_field):
        norm["contato_norm"] = normalizar_contato_field(contato_field)
        if not norm["contato_norm"]:
            return "Contato Field inválido.", norm

    return None, norm


def data_agendamento_anterior_hoje(data_agendamento, hoje: date) -> str | None:
    if not data_agendamento:
        return None
    try:
        dt = datetime.strptime(str(data_agendamento)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    if dt < hoje:
        return f"Data {dt.strftime('%d/%m/%Y')} é anterior a hoje."
    return None


_MOTIVOS_NAO_CORRIGIVEIS = (
    "unidade já possui atendimento concluído",
    "unidade não encontrada",
    "unidade inativa",
    "unidade já processada neste arquivo",
    "duplicado no arquivo",
    "erro ao processar o registro",
    "unidade ha exige",
    "unidade já possui atendimento ativo",
    "inativo/finalizado",
    "já iniciado",
)


def motivo_agendamento_csv_corrigivel(motivo: str | None) -> bool:
    """False quando o motivo não admite correção no portal (concluído, VGR inexistente...)."""
    m = str(motivo or "").strip().lower()
    if not m:
        return False
    return not any(fragmento in m for fragmento in _MOTIVOS_NAO_CORRIGIVEIS)
