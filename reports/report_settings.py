"""Personalização dos reports automáticos (Ajustes operacionais → Personalização dos reports).

Cada report tem um JSON na tabela ``kvs`` (chave ``REPORT_CFG_<ID>``). Campos ausentes
ou chave vazia caem no padrão derivado do ``.env`` — o servidor continua decidindo se
o report pode rodar (flags *_ENABLED do .env iniciam os agendadores).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from core.reports.env_config import (
    DEFAULT_SUPERVISORES_FILA_TO,
    DEFAULT_SUPERVISORES_MACRO_TO,
    env_bool,
    env_int,
    parse_recipients,
)

logger = logging.getLogger(__name__)

REPORT_IDS = ("MACRO", "FUST", "FILA", "GESTAO", "TBRA")
KVS_PREFIX = "REPORT_CFG_"

INTERVALO_MIN = 5
INTERVALO_MAX = 1440
MAX_EMAILS = 60
MAX_FERIADOS = 120
MAX_HORARIOS = 24

_RE_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RE_DATA_BR = re.compile(r"^\d{2}([-/])\d{2}\1\d{4}$")
_RE_EMAIL = re.compile(r"^[^@\s;,<>\"']+@[^@\s;,<>\"']+\.[^@\s;,<>\"']+$")


@dataclass(frozen=True)
class ReportSpec:
    id: str
    label: str
    descricao: str
    canais: tuple[str, ...]
    condicionais: tuple[str, ...]
    agenda_horarios: bool = True
    final_encerra_periodico: bool = True
    rotulo_intervalo: str = "Enviar a cada"


SPECS: dict[str, ReportSpec] = {
    "MACRO": ReportSpec(
        id="MACRO",
        label="Macro FUST + PRODESP",
        descricao="KPIs consolidados FUST + PRODESP para os supervisores.",
        canais=("email", "teams"),
        condicionais=("skip_sem_dados", "skip_igual", "final_so_com_atividade", "parar_dia_encerrado"),
    ),
    "FUST": ReportSpec(
        id="FUST",
        label="FUST-only (Teams)",
        descricao="Cartão dedicado FUST, sem PRODESP (webhook FUST).",
        canais=("teams",),
        condicionais=("skip_sem_dados", "skip_igual", "final_so_com_atividade", "parar_dia_encerrado"),
    ),
    "FILA": ReportSpec(
        id="FILA",
        label="Fila / Analistas disponíveis",
        descricao=(
            "Dispara na hora em que uma unidade nova passa do limiar e relembra a fila "
            "inteira no intervalo escolhido."
        ),
        canais=("email", "teams"),
        condicionais=("skip_igual", "fila_limiar_min"),
        final_encerra_periodico=False,
        rotulo_intervalo="Relembrar a cada",
    ),
    "GESTAO": ReportSpec(
        id="GESTAO",
        label="PRODESP Gestão",
        descricao="Relatório executivo PRODESP (painel de gestão) com anexo XLSX.",
        canais=("email",),
        condicionais=("skip_sem_dados", "skip_igual", "final_so_com_atividade", "parar_dia_encerrado"),
    ),
    "TBRA": ReportSpec(
        id="TBRA",
        label="PRODESP Time TBRA",
        descricao="Relatório executivo PRODESP do Time TBRA com anexo XLSX.",
        canais=("email",),
        condicionais=("skip_sem_dados", "skip_igual", "final_so_com_atividade", "parar_dia_encerrado"),
    ),
}


@dataclass
class ReportConfig:
    report_id: str
    enabled: bool = True
    email_enabled: bool = True
    teams_enabled: bool = True
    agenda_modo: str = "intervalo"
    hora_inicio: str = "10:00"
    hora_fim: str = "18:00"
    intervalo_min: int = 30
    horarios: list[str] = field(default_factory=list)
    dias_semana: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    feriados: list[str] = field(default_factory=list)
    emails_to: list[str] = field(default_factory=list)
    emails_cc: list[str] = field(default_factory=list)
    final_enabled: bool = True
    final_hora: str = "18:00"
    skip_sem_dados: bool = True
    skip_igual: bool = False
    final_so_com_atividade: bool = False
    parar_dia_encerrado: bool = False
    fila_limiar_min: int = 30

    @property
    def spec(self) -> ReportSpec:
        return SPECS[self.report_id]

    @property
    def email_ativo(self) -> bool:
        return self.enabled and self.email_enabled and "email" in self.spec.canais

    @property
    def teams_ativo(self) -> bool:
        return self.enabled and self.teams_enabled and "teams" in self.spec.canais

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResultadoEnvio:
    """Resultado de um envio agendado. Truthy só quando algo saiu."""

    enviado: bool = False
    motivo: str = ""

    def __bool__(self) -> bool:
        return self.enviado

    @property
    def slot_concluido(self) -> bool:
        return self.enviado or self.motivo not in ("falha", "pendente")


ENVIADO = ResultadoEnvio(True)


def omitido(motivo: str) -> ResultadoEnvio:
    return ResultadoEnvio(False, motivo)


def kvs_key(report_id: str) -> str:
    return KVS_PREFIX + report_id


def _hh(hora: int, minuto: int = 0) -> str:
    h = max(0, min(23, int(hora)))
    m = max(0, min(59, int(minuto)))
    return f"{h:02d}:{m:02d}"


def _hora_env(nome: str, default: int) -> str:
    return _hh(env_int(nome, default))


def _defaults_macro(report_id: str) -> ReportConfig:
    email_on = env_bool("SUPERVISORES_MACRO_EMAIL_ENABLED", default=False)
    teams_on = env_bool("SUPERVISORES_MACRO_TEAMS_ENABLED", default=False)
    fim = _hora_env("SUPERVISORES_MACRO_HORA_FIM", 18)
    return ReportConfig(
        report_id=report_id,
        enabled=True,
        email_enabled=email_on if report_id == "MACRO" else False,
        teams_enabled=teams_on,
        hora_inicio=_hora_env("SUPERVISORES_MACRO_HORA_INICIO", 10),
        hora_fim=fim,
        intervalo_min=30,
        emails_to=parse_recipients(os.getenv("SUPERVISORES_MACRO_EMAIL_TO"), DEFAULT_SUPERVISORES_MACRO_TO)
        if report_id == "MACRO"
        else [],
        final_enabled=env_bool("SUPERVISORES_MACRO_FINAL_ENABLED", default=True),
        final_hora=fim,
        skip_sem_dados=env_bool("SUPERVISORES_MACRO_SKIP_VAZIO", default=True),
    )


def _defaults_fila() -> ReportConfig:
    sempre = env_bool("SUPERVISORES_FILA_SEMPRE", default=True)
    return ReportConfig(
        report_id="FILA",
        enabled=True,
        email_enabled=env_bool("SUPERVISORES_FILA_EMAIL_ENABLED", default=False),
        teams_enabled=env_bool("SUPERVISORES_FILA_TEAMS_ENABLED", default=False),
        hora_inicio="00:00" if sempre else _hora_env("SUPERVISORES_FILA_HORA_INICIO", 8),
        hora_fim="23:59" if sempre else _hora_env("SUPERVISORES_FILA_HORA_FIM", 19),
        intervalo_min=max(INTERVALO_MIN, env_int("SUPERVISORES_FILA_RELEMBRE_MINUTOS", 15)),
        dias_semana=[0, 1, 2, 3, 4, 5, 6] if sempre else [0, 1, 2, 3, 4],
        emails_to=parse_recipients(os.getenv("SUPERVISORES_FILA_EMAIL_TO"), DEFAULT_SUPERVISORES_FILA_TO),
        final_enabled=env_bool("SUPERVISORES_FILA_FINAL_ENABLED", default=True),
        final_hora=_hora_env("SUPERVISORES_FILA_HORA_FIM", 19),
        skip_sem_dados=True,
        fila_limiar_min=max(1, env_int("SUPERVISORES_FILA_MINUTOS", 30)),
    )


def _defaults_gestao() -> ReportConfig:
    from prodesp.prodesp.gestao.gestao_relatorio_email import recipients_gestao_from_env

    fim = _hora_env("PRODESP_GESTAO_RELATORIO_HORA_FIM", 18)
    return ReportConfig(
        report_id="GESTAO",
        enabled=True,
        email_enabled=True,
        teams_enabled=False,
        hora_inicio=_hora_env("PRODESP_GESTAO_RELATORIO_HORA_INICIO", 10),
        hora_fim=fim,
        intervalo_min=30,
        emails_to=recipients_gestao_from_env(),
        final_enabled=env_bool("PRODESP_GESTAO_RELATORIO_FINAL_ENABLED", default=True),
        final_hora=fim,
        skip_sem_dados=env_bool("PRODESP_GESTAO_RELATORIO_SKIP_VAZIO", default=True),
        final_so_com_atividade=True,
        parar_dia_encerrado=True,
    )


def _defaults_tbra() -> ReportConfig:
    from prodesp.prodesp.gestao.tbra_relatorio_email import recipients_tbra_from_env
    from prodesp.prodesp.gestao.tbra_relatorio_scheduler import horarios_tbra_from_env

    horas = horarios_tbra_from_env()
    return ReportConfig(
        report_id="TBRA",
        enabled=True,
        email_enabled=True,
        teams_enabled=False,
        agenda_modo="horarios",
        hora_inicio=_hh(min(horas)),
        hora_fim=_hh(max(horas)),
        intervalo_min=60,
        horarios=[_hh(h) for h in horas],
        emails_to=recipients_tbra_from_env(),
        final_enabled=env_bool("PRODESP_TIME_TBRA_RELATORIO_FINAL_ENABLED", default=True),
        final_hora=_hh(max(horas)),
        skip_sem_dados=env_bool("PRODESP_TIME_TBRA_RELATORIO_SKIP_VAZIO", default=True),
        final_so_com_atividade=True,
        parar_dia_encerrado=True,
    )


def config_padrao(report_id: str) -> ReportConfig:
    if report_id in ("MACRO", "FUST"):
        return _defaults_macro(report_id)
    if report_id == "FILA":
        return _defaults_fila()
    if report_id == "GESTAO":
        return _defaults_gestao()
    if report_id == "TBRA":
        return _defaults_tbra()
    raise ValueError(f"report invalido: {report_id!r}")


ENV_FLAGS_SERVIDOR: dict[str, tuple[str, ...]] = {
    "MACRO": ("SUPERVISORES_MACRO_EMAIL_ENABLED", "SUPERVISORES_MACRO_TEAMS_ENABLED"),
    "FUST": ("SUPERVISORES_MACRO_TEAMS_ENABLED",),
    "FILA": ("SUPERVISORES_FILA_EMAIL_ENABLED", "SUPERVISORES_FILA_TEAMS_ENABLED"),
    "GESTAO": ("PRODESP_GESTAO_RELATORIO_EMAIL_ENABLED",),
    "TBRA": ("PRODESP_TIME_TBRA_RELATORIO_EMAIL_ENABLED",),
}


def report_permitido_no_servidor(report_id: str) -> bool:
    """Flags do .env que ligam o agendador desta instância (a UI não liga o que o .env desligou)."""
    return any(env_bool(nome) for nome in ENV_FLAGS_SERVIDOR.get(report_id, ()))


def _ler_override(report_id: str) -> dict[str, Any] | None:
    try:
        from login.models import LoginDynamicSettings

        raw = (LoginDynamicSettings.get(kvs_key(report_id)) or "").strip()
    except Exception:
        logger.debug("reports - kvs indisponível para %s", report_id)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("reports - config %s inválida no kvs; usando .env", report_id)
        return None
    return data if isinstance(data, dict) else None


def tem_override(report_id: str) -> bool:
    return _ler_override(report_id) is not None


def carregar_config(report_id: str) -> ReportConfig:
    base = config_padrao(report_id)
    override = _ler_override(report_id)
    if not override:
        return base
    cfg, _erros = normalizar_config(report_id, override, base=base, estrito=False)
    return cfg


def salvar_config(cfg: ReportConfig) -> None:
    from login.models import LoginDynamicSettings

    LoginDynamicSettings.set(kvs_key(cfg.report_id), json.dumps(cfg.to_dict(), ensure_ascii=False))


def restaurar_padrao(report_id: str) -> None:
    from login.models import LoginDynamicSettings

    LoginDynamicSettings.set(kvs_key(report_id), "")


def _bool(val: Any, default: bool) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return int(val) != 0
    return str(val).strip().lower() in ("1", "true", "yes", "sim", "on")


def _lista_texto(val: Any) -> list[str]:
    if val is None:
        return []
    if isinstance(val, str):
        partes = val.replace(",", ";").replace("\n", ";").split(";")
    elif isinstance(val, Iterable):
        partes = [str(v) for v in val]
    else:
        return []
    saida: list[str] = []
    for p in partes:
        t = str(p).strip()
        if t and t not in saida:
            saida.append(t)
    return saida


def _emails(val: Any, campo: str, erros: list[str]) -> list[str]:
    saida: list[str] = []
    for e in _lista_texto(val):
        if not _RE_EMAIL.match(e):
            erros.append(f"{campo}: e-mail inválido ({e[:80]})")
            continue
        if e.lower() not in (x.lower() for x in saida):
            saida.append(e)
    if len(saida) > MAX_EMAILS:
        erros.append(f"{campo}: máximo de {MAX_EMAILS} e-mails")
        saida = saida[:MAX_EMAILS]
    return saida


def _hora(val: Any, campo: str, default: str, erros: list[str]) -> str:
    s = str(val or "").strip()[:5]
    if _RE_HORA.match(s):
        return s
    erros.append(f"{campo}: use HH:MM")
    return default


def _data_iso(texto: str) -> str | None:
    """Aceita DD-MM-AAAA ou DD/MM/AAAA (tela) e AAAA-MM-DD (já gravado); devolve AAAA-MM-DD."""
    s = str(texto or "").strip()
    if _RE_DATA_BR.match(s):
        formato = "%d-%m-%Y" if "-" in s else "%d/%m/%Y"
    elif _RE_DATA.match(s):
        formato = "%Y-%m-%d"
    else:
        return None
    try:
        return datetime.strptime(s, formato).strftime("%Y-%m-%d")
    except ValueError:
        return None


def minutos_do_dia(hora: str) -> int:
    m = _RE_HORA.match(hora or "")
    if not m:
        return 0
    return int(m.group(1)) * 60 + int(m.group(2))


def normalizar_config(
    report_id: str,
    payload: Mapping[str, Any],
    *,
    base: ReportConfig | None = None,
    estrito: bool = True,
) -> tuple[ReportConfig, list[str]]:
    """Valida e aplica ``payload`` sobre ``base``. Retorna (config, erros)."""
    if report_id not in SPECS:
        raise ValueError(f"report invalido: {report_id!r}")
    spec = SPECS[report_id]
    cfg = replace(base) if base is not None else config_padrao(report_id)
    erros: list[str] = []
    p = dict(payload or {})

    for nome in ("enabled", "email_enabled", "teams_enabled", "final_enabled"):
        if nome in p:
            setattr(cfg, nome, _bool(p[nome], getattr(cfg, nome)))
    for nome in spec.condicionais:
        if nome == "fila_limiar_min" or nome not in p:
            continue
        setattr(cfg, nome, _bool(p[nome], getattr(cfg, nome)))

    if "agenda_modo" in p:
        modo = str(p.get("agenda_modo") or "").strip()
        if modo == "horarios" and spec.agenda_horarios:
            cfg.agenda_modo = "horarios"
        elif modo == "intervalo":
            cfg.agenda_modo = "intervalo"
        else:
            erros.append("agenda_modo inválido")
    if not spec.agenda_horarios:
        cfg.agenda_modo = "intervalo"

    for nome in ("hora_inicio", "hora_fim", "final_hora"):
        if nome in p:
            setattr(cfg, nome, _hora(p[nome], nome, getattr(cfg, nome), erros))
    if minutos_do_dia(cfg.hora_inicio) > minutos_do_dia(cfg.hora_fim):
        erros.append("hora_inicio deve ser menor ou igual a hora_fim")

    if "intervalo_min" in p:
        try:
            n = int(p["intervalo_min"])
        except (TypeError, ValueError):
            n = -1
        if INTERVALO_MIN <= n <= INTERVALO_MAX:
            cfg.intervalo_min = n
        else:
            erros.append(f"intervalo_min entre {INTERVALO_MIN} e {INTERVALO_MAX} minutos")

    if "horarios" in p:
        horas: list[str] = []
        for h in _lista_texto(p["horarios"]):
            h5 = h[:5]
            if _RE_HORA.match(h5):
                if h5 not in horas:
                    horas.append(h5)
            else:
                erros.append(f"horarios: use HH:MM ({h[:10]})")
        cfg.horarios = sorted(horas, key=minutos_do_dia)[:MAX_HORARIOS]
    if cfg.agenda_modo == "horarios" and not cfg.horarios:
        erros.append("informe ao menos um horário fixo")

    if "dias_semana" in p:
        dias: list[int] = []
        for d in p.get("dias_semana") or []:
            try:
                n = int(d)
            except (TypeError, ValueError):
                continue
            if 0 <= n <= 6 and n not in dias:
                dias.append(n)
        cfg.dias_semana = sorted(dias)
        if not dias:
            erros.append("selecione ao menos um dia da semana")

    if "feriados" in p:
        datas: list[str] = []
        for bruto in _lista_texto(p["feriados"]):
            d = _data_iso(bruto)
            if d is None:
                erros.append(f"feriados: use DD-MM-AAAA ({bruto[:12]})")
                continue
            if d not in datas:
                datas.append(d)
        cfg.feriados = sorted(datas)[:MAX_FERIADOS]

    if "email" in spec.canais:
        if "emails_to" in p:
            cfg.emails_to = _emails(p["emails_to"], "emails_to", erros)
        if "emails_cc" in p:
            cfg.emails_cc = _emails(p["emails_cc"], "emails_cc", erros)
        if cfg.email_enabled and not cfg.emails_to:
            erros.append("e-mail habilitado sem destinatário principal")
    else:
        cfg.email_enabled = False
        cfg.emails_to = []
        cfg.emails_cc = []
    if "teams" not in spec.canais:
        cfg.teams_enabled = False

    if "fila_limiar_min" in spec.condicionais and "fila_limiar_min" in p:
        try:
            n = int(p["fila_limiar_min"])
        except (TypeError, ValueError):
            n = -1
        if 1 <= n <= INTERVALO_MAX:
            cfg.fila_limiar_min = n
        else:
            erros.append(f"fila_limiar_min entre 1 e {INTERVALO_MAX} minutos")

    if not estrito and erros:
        logger.warning("reports - config %s com campos inválidos ignorados: %s", report_id, erros[:5])
    return cfg, erros


# ---------------------------------------------------------------- agenda


def dia_permitido(cfg: ReportConfig, now: datetime) -> bool:
    if now.weekday() not in cfg.dias_semana:
        return False
    return now.strftime("%Y-%m-%d") not in cfg.feriados


def fim_periodico_min(cfg: ReportConfig) -> int:
    if cfg.agenda_modo == "horarios" and cfg.horarios:
        fim = max(minutos_do_dia(h) for h in cfg.horarios)
    else:
        fim = minutos_do_dia(cfg.hora_fim)
    if cfg.final_enabled and cfg.spec.final_encerra_periodico:
        fim = min(fim, minutos_do_dia(cfg.final_hora))
    return fim


def dentro_janela(cfg: ReportConfig, now: datetime) -> bool:
    if not dia_permitido(cfg, now):
        return False
    m = now.hour * 60 + now.minute
    return minutos_do_dia(cfg.hora_inicio) <= m <= minutos_do_dia(cfg.hora_fim)


def slot_periodico(cfg: ReportConfig, now: datetime) -> str | None:
    """Chave do slot periódico vigente (None fora da agenda). Um envio por slot."""
    if not dia_permitido(cfg, now):
        return None
    dia = now.strftime("%Y-%m-%d")
    m = now.hour * 60 + now.minute
    fim = fim_periodico_min(cfg)
    if cfg.agenda_modo == "horarios":
        passados = [
            minutos_do_dia(h)
            for h in cfg.horarios
            if minutos_do_dia(h) <= m < minutos_do_dia(h) + 60 and minutos_do_dia(h) <= fim
        ]
        if not passados:
            return None
        h = max(passados)
        return f"{dia} H{h // 60:02d}:{h % 60:02d}"
    ini = minutos_do_dia(cfg.hora_inicio)
    if m < ini or m > fim:
        return None
    n = (m - ini) // max(1, cfg.intervalo_min)
    return f"{dia} #{n}"


def final_devido(cfg: ReportConfig, now: datetime) -> bool:
    if not cfg.final_enabled or not dia_permitido(cfg, now):
        return False
    m = now.hour * 60 + now.minute
    if m < minutos_do_dia(cfg.final_hora):
        return False
    if cfg.spec.final_encerra_periodico and m <= fim_periodico_min(cfg):
        return False
    return True


# ---------------------------------------------------------------- "igual ao anterior"


_fp_lock = threading.Lock()
_ultimo_fp: dict[str, tuple[str, str]] = {}


def _contagens(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _contagens(getattr(obj, f.name)) for f in fields(obj) if not f.name.startswith("_")}
    if isinstance(obj, Mapping):
        return {str(k): _contagens(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple, set)):
        return [_contagens(v) for v in obj]
    if isinstance(obj, bool) or isinstance(obj, int):
        return obj
    if obj is None or isinstance(obj, str):
        return obj
    return None


def fingerprint(*partes: Any) -> str:
    """Assinatura dos números do report (tempos/strings livres ficam de fora)."""

    def limpar(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: limpar(x) for k, x in v.items() if not isinstance(x, str)}
        if isinstance(v, list):
            return [limpar(x) for x in v]
        return v

    return json.dumps([limpar(_contagens(p)) for p in partes], sort_keys=True, default=str)


def igual_ao_ultimo(report_id: str, dia: str, fp: str) -> bool:
    with _fp_lock:
        atual = _ultimo_fp.get(report_id)
    return atual is not None and atual == (dia, fp)


def registrar_envio(report_id: str, dia: str, fp: str) -> None:
    with _fp_lock:
        _ultimo_fp[report_id] = (dia, fp)


def limpar_fingerprints() -> None:
    with _fp_lock:
        _ultimo_fp.clear()


# ---------------------------------------------------------------- tick genérico


def executar_tick(
    report_id: str,
    now: datetime,
    estado: dict[str, Any],
    enviar_periodico: Callable[[], ResultadoEnvio],
    enviar_final: Callable[[], ResultadoEnvio],
) -> None:
    """Um passo do agendador: periódico no slot novo; Final 1×/dia quando devido."""
    cfg = carregar_config(report_id)
    dia = now.strftime("%Y-%m-%d")
    if estado.get("final_dia") and estado["final_dia"] != dia:
        estado["final_dia"] = None
    if not cfg.enabled or not (cfg.email_ativo or cfg.teams_ativo):
        return
    slot = slot_periodico(cfg, now)
    if slot and slot != estado.get("slot"):
        res = enviar_periodico()
        if res.slot_concluido:
            estado["slot"] = slot
        logger.info("reports - %s periódico slot %s: %s", report_id, slot, res.motivo or "enviado")
        if (
            res.motivo == "encerrado"
            and cfg.final_enabled
            and estado.get("final_dia") != dia
        ):
            fin = enviar_final()
            if fin.enviado or fin.motivo in ("sem_dados", "sem_atividade", "desabilitado"):
                estado["final_dia"] = dia
        return
    if estado.get("final_dia") != dia and final_devido(cfg, now):
        fin = enviar_final()
        if fin.enviado or fin.motivo in ("sem_dados", "sem_atividade", "desabilitado"):
            estado["final_dia"] = dia
            logger.info("reports - %s Report Final (%s): %s", report_id, dia, fin.motivo or "enviado")
