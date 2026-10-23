"""Fila Aguardando Config. Remota sem analista alocado (≥ N minutos)."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

import pytz

from core.reports.kpi_macro import SUB_FILA_REMOTA, segundos_hhmmss

TZ_SP = pytz.timezone("America/Sao_Paulo")
logger = logging.getLogger(__name__)


def _txt(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def analista_alocado(row: Mapping[str, Any]) -> str:
    return _txt(row, "analista_configuracao_atendimentos", "analista_configuracao")


def sem_analista_config(row: Mapping[str, Any]) -> bool:
    return not analista_alocado(row)


def as_datetime(val: Any) -> Optional[datetime]:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        dt = val
    else:
        s = str(val).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(s[:19], fmt)
                break
            except ValueError:
                dt = None
        else:
            return None
        if dt is None:
            return None
    if dt.tzinfo is None:
        return TZ_SP.localize(dt)
    return dt.astimezone(TZ_SP)


@dataclass
class FilaEsperaItem:
    projeto: str
    id_atendimento: int
    chave: str
    unidade: str
    municipio: str
    uf: str
    entrou_em: Optional[datetime]
    espera_seg: int
    analista: str = ""
    usuario_saida: str = ""
    avisos: int = 0
    qtd_acionamentos_ate_assumido: int = 0

    @property
    def espera_label(self) -> str:
        return segundos_hhmmss(self.espera_seg)

    @property
    def avisos_label(self) -> str:
        n = max(0, int(self.avisos or 0))
        if n <= 0:
            return "—"
        return f"{n}ª vez"

    @property
    def acionamentos_label(self) -> str:
        n = max(0, int(self.qtd_acionamentos_ate_assumido or 0))
        if n <= 0:
            return "—"
        if n == 1:
            return "1 vez"
        return f"{n} vezes"


def espera_desde(entrou_em: Optional[datetime], agora: Optional[datetime] = None) -> int:
    if not entrou_em:
        return 0
    now = agora or datetime.now(TZ_SP)
    if now.tzinfo is None:
        now = TZ_SP.localize(now)
    start = entrou_em if entrou_em.tzinfo else TZ_SP.localize(entrou_em)
    return max(0, int((now - start).total_seconds()))


def filtrar_fila_atual(
    itens: Iterable[FilaEsperaItem],
    *,
    minutos_min: int = 30,
) -> list[FilaEsperaItem]:
    limiar = max(0, int(minutos_min)) * 60
    saida = [i for i in itens if i.espera_seg >= limiar and not str(i.analista or "").strip()]
    saida.sort(key=lambda x: x.espera_seg, reverse=True)
    return saida


def chave_fila(item: FilaEsperaItem) -> tuple[str, int]:
    return (str(item.projeto), int(item.id_atendimento))


def itens_ainda_nao_alertados(
    itens: Iterable[FilaEsperaItem],
    ja_alertados: set[tuple[str, int]],
) -> tuple[list[FilaEsperaItem], set[tuple[str, int]]]:
    """Novos ≥ limiar ainda não avisados; devolve também as chaves ainda na fila."""
    lista = list(itens)
    atuais = {chave_fila(i) for i in lista}
    vigentes = set(ja_alertados) & atuais
    novos = [i for i in lista if chave_fila(i) not in vigentes]
    return novos, vigentes


def podar_contagem_avisos(
    contagem: dict[tuple[str, int], int],
    itens: Iterable[FilaEsperaItem],
) -> dict[tuple[str, int], int]:
    vigentes = {chave_fila(i) for i in itens}
    return {k: v for k, v in contagem.items() if k in vigentes}


def deve_enviar_snapshot_fila(
    itens: Iterable[FilaEsperaItem],
    contagem_avisos: Mapping[tuple[str, int], int],
    agora: datetime,
    ultimo_envio: Optional[datetime],
    *,
    relembre_min: int = 15,
) -> bool:
    """Envia se há fila ≥ limiar e (unidade nova ou já passou o intervalo de relembre)."""
    lista = list(itens)
    if not lista:
        return False
    if any(chave_fila(i) not in contagem_avisos for i in lista):
        return True
    if ultimo_envio is None:
        return True
    agora_tz = agora if agora.tzinfo else TZ_SP.localize(agora)
    ultimo_tz = ultimo_envio if ultimo_envio.tzinfo else TZ_SP.localize(ultimo_envio)
    limiar = max(1, int(relembre_min)) * 60
    return (agora_tz - ultimo_tz).total_seconds() >= limiar


def aplicar_proximo_aviso(
    itens: Iterable[FilaEsperaItem],
    contagem_avisos: Mapping[tuple[str, int], int],
) -> list[FilaEsperaItem]:
    """Preenche avisos = vezes anteriores + 1 (o envio que está saindo agora)."""
    saida = list(itens)
    for item in saida:
        item.avisos = int(contagem_avisos.get(chave_fila(item), 0)) + 1
    return saida


def registrar_envio_avisos(
    contagem_avisos: dict[tuple[str, int], int],
    itens: Iterable[FilaEsperaItem],
) -> None:
    for item in itens:
        contagem_avisos[chave_fila(item)] = max(1, int(item.avisos or 1))


def _chave_store(chave: tuple[str, int]) -> str:
    return f"{chave[0]}|{int(chave[1])}"


def _parse_chave_store(raw: str) -> tuple[str, int] | None:
    if "|" not in raw:
        return None
    projeto, _, id_txt = raw.partition("|")
    try:
        return (projeto.strip(), int(id_txt))
    except (TypeError, ValueError):
        return None


def caminho_avisos() -> Path:
    raw = (os.getenv("SUPERVISORES_FILA_AVISOS_PATH") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2] / "temporario" / "supervisores_fila_avisos.json"


def carregar_contagem_avisos() -> dict[tuple[str, int], int]:
    path = caminho_avisos()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("supervisores - falha ao ler contagem de avisos")
        return {}
    saida: dict[tuple[str, int], int] = {}
    if not isinstance(data, dict):
        return saida
    for k, v in data.items():
        chave = _parse_chave_store(str(k))
        if not chave:
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > 0:
            saida[chave] = n
    return saida


def salvar_contagem_avisos(contagem: Mapping[tuple[str, int], int]) -> None:
    path = caminho_avisos()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {_chave_store(k): int(v) for k, v in contagem.items() if int(v) > 0}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError:
        logger.warning("supervisores - falha ao gravar contagem de avisos")


def intervalos_fila_do_log(
    eventos: list[Mapping[str, Any]],
    *,
    agora: Optional[datetime] = None,
    sub_alvo: str = SUB_FILA_REMOTA,
) -> list[tuple[datetime, Optional[datetime], str]]:
    """Retorna (inicio, fim|None se aberto, usuario_saida) de cada trecho na fila remota."""
    now = agora or datetime.now(TZ_SP)
    trechos: list[tuple[datetime, Optional[datetime], str]] = []
    aberto: Optional[datetime] = None
    for ev in eventos or []:
        novo = _txt(ev, "valor_novo_log", "status", "valor_novo")
        quando = as_datetime(ev.get("alterado_em_log") or ev.get("changed_at"))
        if not quando:
            continue
        if novo == sub_alvo:
            if aberto is None:
                aberto = quando
            continue
        if aberto is not None:
            usuario = _txt(ev, "usuario_log", "usuario")
            trechos.append((aberto, quando, usuario))
            aberto = None
    if aberto is not None:
        trechos.append((aberto, None, ""))
        _ = now
    return trechos


def total_acionamentos_fila_do_log(
    eventos: list[Mapping[str, Any]],
    *,
    sub_alvo: str = SUB_FILA_REMOTA,
) -> int:
    """Total de vezes em que o atendimento entrou na fila remota (inclui intervalos já encerrados e aberto atual)."""
    return len(intervalos_fila_do_log(eventos, sub_alvo=sub_alvo))


def preencher_acionamentos_ate_assumido(
    itens: list[FilaEsperaItem],
    *,
    evento_por_id: Mapping[int, list[Mapping[str, Any]]],
    sub_alvo: str = SUB_FILA_REMOTA,
) -> None:
    """Preenche `qtd_acionamentos_ate_assumido` em cada item a partir do log de substatus."""
    for it in itens:
        try:
            id_att = int(it.id_atendimento or 0)
        except (TypeError, ValueError):
            continue
        eventos = evento_por_id.get(id_att) or []
        total = total_acionamentos_fila_do_log(eventos, sub_alvo=sub_alvo)
        it.qtd_acionamentos_ate_assumido = max(it.qtd_acionamentos_ate_assumido or 0, int(total or 0))


def itens_final_do_log(
    *,
    projeto: str,
    id_atendimento: int,
    chave: str,
    unidade: str,
    municipio: str,
    uf: str,
    analista_atual: str,
    eventos: list[Mapping[str, Any]],
    minutos_min: int = 30,
    agora: Optional[datetime] = None,
) -> list[FilaEsperaItem]:
    """Trechos encerrados (≥ limiar) — quem atendeu e quanto ficou parado."""
    now = agora or datetime.now(TZ_SP)
    limiar = max(0, int(minutos_min)) * 60
    acionamentos = total_acionamentos_fila_do_log(eventos)
    saida: list[FilaEsperaItem] = []
    for inicio, fim, usuario in intervalos_fila_do_log(eventos, agora=now):
        if fim is None:
            continue
        espera = max(0, int((fim - inicio).total_seconds()))
        if espera < limiar:
            continue
        saida.append(
            FilaEsperaItem(
                projeto=projeto,
                id_atendimento=id_atendimento,
                chave=chave,
                unidade=unidade,
                municipio=municipio,
                uf=uf,
                entrou_em=inicio,
                espera_seg=espera,
                analista=analista_atual or usuario,
                usuario_saida=usuario,
                qtd_acionamentos_ate_assumido=acionamentos,
            )
        )
    return saida
