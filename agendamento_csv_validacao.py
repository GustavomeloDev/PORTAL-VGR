"""
Validação de linhas do CSV de agendamento PRODESP (portal + testes).
"""
from __future__ import annotations

from datetime import date, datetime

CONTRATADAS_PERMITIDAS = sorted([
    "DELFIA",
    "INELCOM",
    "MAMInfo",
    "SPREAD",
    "Vivo Redes - Capital",
    "Vivo Redes - Interior",
])

MSG_DUPLICATA_VGR = (
    "ID VGR duplicado no arquivo (segunda ocorrência ignorada; mantida a primeira)."
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

FIELD_MAX_CHARS = 60
CONTATO_MIN_DIGITS = 10
CONTATO_MAX_DIGITS = 11


def csv_valor_ausente(val) -> bool:
    if val is None:
        return True
    s = str(val).strip().lower()
    return not s or s in _CSV_PLACEHOLDERS_VAZIOS


def normalizar_contato_field_planejado(val):
    if val is None:
        return None
    digits = "".join(c for c in str(val) if c.isdigit())
    return digits[:20] if digits else None


def validar_id_vgr_csv(id_vgr: str) -> str | None:
    s = str(id_vgr or "").strip()
    if not s:
        return "ID VGR obrigatório."
    if not s.isdigit():
        return f"ID VGR inválido ({s}). Use somente números."
    return None


def validar_contratada_planejada(val) -> tuple[str | None, str | None]:
    if csv_valor_ausente(val):
        return None, None
    bruto = str(val).strip()
    for permitida in CONTRATADAS_PERMITIDAS:
        if permitida.lower() == bruto.lower():
            return permitida, None
    lista = ", ".join(CONTRATADAS_PERMITIDAS)
    return None, f"Contratada inválida ({bruto}). Valores permitidos: {lista}"


def _canonical_contratada_lista(val: str) -> str | None:
    bruto = str(val or "").strip()
    if not bruto:
        return None
    for permitida in CONTRATADAS_PERMITIDAS:
        if permitida.lower() == bruto.lower():
            return permitida
    return None


def validar_data_agendamento_csv(data_agendamento, *, obrigatoria: bool = False) -> str | None:
    if not data_agendamento:
        if obrigatoria:
            return "Data de agendamento obrigatória."
        return None
    bruto = str(data_agendamento).strip()
    try:
        datetime.strptime(bruto[:10], "%Y-%m-%d").date()
    except ValueError:
        return f"Data inválida ({bruto}). Use dd/mm/yyyy."
    return None


def validar_field_contratada_csv(
    contratada_canonica: str | None,
    field_planejado,
) -> str | None:
    if csv_valor_ausente(field_planejado) or not contratada_canonica:
        return None
    field_canonica = _canonical_contratada_lista(str(field_planejado).strip())
    if field_canonica and field_canonica != contratada_canonica:
        return (
            f"Field ({field_canonica}) não corresponde à contratada ({contratada_canonica}). "
            "Quando Field é uma empresa da lista oficial, deve ser igual à contratada."
        )
    return None


def validar_field_contato_csv(field_planejado, contato_field) -> tuple[str | None, str | None]:
    if csv_valor_ausente(field_planejado):
        return None, None
    field_txt = str(field_planejado).strip()
    if len(field_txt) > FIELD_MAX_CHARS:
        return "Field excede 60 caracteres.", None
    contato_norm = normalizar_contato_field_planejado(contato_field)
    if (
        not contato_norm
        or len(contato_norm) < CONTATO_MIN_DIGITS
        or len(contato_norm) > CONTATO_MAX_DIGITS
    ):
        return "Contato Field obrigatório (10 ou 11 dígitos) quando Field está preenchido.", None
    return None, contato_norm


def validar_agendamento_csv_linha(
    *,
    id_vgr: str,
    data_agendamento,
    hora_agendamento,
    contratada,
    field_planejado=None,
    contato_field=None,
    tem_agenda: bool,
    normalize_hora_fn,
) -> tuple[str | None, str | None, str | None, str | None]:
    """
    Retorna (erro, hora_norm, contratada_canonica, contato_norm).
    """
    err_id = validar_id_vgr_csv(id_vgr)
    if err_id:
        return err_id, None, None, None

    hora_norm: str | None = None
    contratada_canonica: str | None = None
    contato_norm: str | None = None

    if tem_agenda:
        err_data = validar_data_agendamento_csv(data_agendamento, obrigatoria=True)
        if err_data:
            return err_data, None, None, None
        if csv_valor_ausente(hora_agendamento):
            return "Hora de agendamento obrigatória.", None, None, None
        hora_norm = normalize_hora_fn(hora_agendamento)
        if not hora_norm:
            bruto = str(hora_agendamento).strip()
            return f"Hora inválida ({bruto}). Use o formato HH:mm.", None, None, None
        if csv_valor_ausente(contratada):
            lista = ", ".join(CONTRATADAS_PERMITIDAS)
            return f"Contratada obrigatória para agendamento. Valores permitidos: {lista}", None, None, None
        contratada_canonica, err = validar_contratada_planejada(contratada)
        if err:
            return err, None, None, None
    else:
        if data_agendamento:
            err_data = validar_data_agendamento_csv(data_agendamento)
            if err_data:
                return err_data, None, None, None
        if not csv_valor_ausente(contratada):
            contratada_canonica, err = validar_contratada_planejada(contratada)
            if err:
                return err, None, None, None
        if not csv_valor_ausente(hora_agendamento):
            hora_norm = normalize_hora_fn(hora_agendamento)
            if not hora_norm:
                bruto = str(hora_agendamento).strip()
                return f"Hora inválida ({bruto}). Use o formato HH:mm.", None, contratada_canonica, None

    err_field, contato_norm = validar_field_contato_csv(field_planejado, contato_field)
    if err_field:
        return err_field, hora_norm, contratada_canonica, None

    err_fc = validar_field_contratada_csv(contratada_canonica, field_planejado)
    if err_fc:
        return err_fc, hora_norm, contratada_canonica, contato_norm

    if contato_field and not csv_valor_ausente(contato_field) and contato_norm is None:
        contato_norm = normalizar_contato_field_planejado(contato_field)
        if not contato_norm:
            return "Contato Field inválido.", hora_norm, contratada_canonica, None

    return None, hora_norm, contratada_canonica, contato_norm


def data_agendamento_anterior_hoje(data_agendamento, hoje: date) -> str | None:
    if not data_agendamento:
        return None
    try:
        dt = datetime.strptime(str(data_agendamento)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    if dt < hoje:
        return f"Data {data_agendamento} é anterior a hoje."
    return None


_MOTIVOS_NAO_CORRIGIVEIS = (
    "unidade já possui atendimento concluído",
    "unidade não encontrada",
    "id vgr duplicado no arquivo",
    "erro ao processar o registro",
)


def motivo_agendamento_csv_corrigivel(motivo: str | None) -> bool:
    """False quando o motivo não admite correção no portal (ex.: concluído, VGR inexistente)."""
    m = str(motivo or "").strip().lower()
    if not m:
        return False
    return not any(fragmento in m for fragmento in _MOTIVOS_NAO_CORRIGIVEIS)
