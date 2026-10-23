"""Picos horários de atendimento simultâneo e fila aguardando analista."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional, Sequence

from core.reports.kpi_macro import SUB_FILA_REMOTA

SUBS_ESPERA_ANALISTA = frozenset(
    {
        SUB_FILA_REMOTA,
        "Aguardando Config. MPLS",
        "Aguardando Caderno de Teste",
    }
)

SUBS_EM_ATENDIMENTO = frozenset(
    {
        "Em Configuração Remota",
        "Em Configuração do MPLS",
        "Em Caderno de Teste",
        "Em atuacao tecnica",
        "Em atuação técnica",
    }
)


@dataclass(frozen=True)
class PicoHora:
    hora_ini: int
    max_simultaneos: int
    analistas_disponiveis: int = 0
    analistas_atuando: int = 0

    @property
    def hora_fim(self) -> int:
        return (self.hora_ini + 1) % 24

    @property
    def label(self) -> str:
        return f"{self.hora_ini:02d}h–{self.hora_fim:02d}h"

    def linha(self, prefixo: str, *, mostrar_equipe: bool = False) -> str:
        n = self.max_simultaneos
        unidade = "atendimento simultâneo" if n == 1 else "atendimentos simultâneos"
        base = f"{prefixo} {self.label} — {n} {unidade}"
        if not mostrar_equipe:
            return base
        disp = int(self.analistas_disponiveis or 0)
        atu = int(self.analistas_atuando or 0)
        return f"{base} · equipe: {disp} disp. / {atu} atuando"


@dataclass
class PicosProjeto:
    projeto: str
    atendimento: list[PicoHora] = field(default_factory=list)
    espera: list[PicoHora] = field(default_factory=list)

    @property
    def tem_dado(self) -> bool:
        return bool(self.atendimento or self.espera)


@dataclass
class PicosDia:
    fust: PicosProjeto = field(default_factory=lambda: PicosProjeto("FUST"))
    prodesp: PicosProjeto = field(default_factory=lambda: PicosProjeto("PRODESP"))
    geral: PicosProjeto = field(default_factory=lambda: PicosProjeto("GERAL"))

    @property
    def tem_dado(self) -> bool:
        return self.fust.tem_dado or self.prodesp.tem_dado or self.geral.tem_dado


EquipeHora = tuple[int, int]
"""Alias: (qtd_disponiveis, qtd_atuando) por hora do dia."""


def equipe_por_hora_do_dia(
    analistas_disponiveis_ids: Sequence[object],
    *,
    atuando_por_hora: Sequence[Iterable[object]],
    dia: datetime,
) -> list[EquipeHora]:
    """Retorna lista de tamanho 24 com (qtd_disp, qtd_atuando_distintos) por hora do dia."""
    disp_ids = set(analistas_disponiveis_ids or [])
    horas: list[EquipeHora] = []
    for h in range(24):
        atu_ids = set()
        if h < len(atuando_por_hora):
            for ident in atuando_por_hora[h] or ():
                atu_ids.add(ident)
        disp = len(disp_ids)
        atu = len(atu_ids)
        horas.append((disp, atu))
    _ = dia
    return horas


def preencher_equipe_picos(
    picos: list[PicoHora],
    *,
    equipe_hora: Sequence[EquipeHora],
) -> list[PicoHora]:
    """Retorna nova lista de PicoHora com analistas_disponiveis/atuando preenchidos a partir da equipe por hora."""
    novas: list[PicoHora] = []
    for p in picos or []:
        disp = 0
        atu = 0
        h = int(p.hora_ini) if 0 <= int(p.hora_ini) < 24 else -1
        if h >= 0 and h < len(equipe_hora):
            disp, atu = equipe_hora[h]
        novas.append(
            PicoHora(
                hora_ini=p.hora_ini,
                max_simultaneos=p.max_simultaneos,
                analistas_disponiveis=int(disp),
                analistas_atuando=int(atu),
            )
        )
    return novas


def intervalos_nos_alvos(
    eventos: Sequence[tuple[datetime, str]],
    *,
    alvos: frozenset[str],
    agora: datetime,
    inicio_fallback: Optional[datetime] = None,
    sub_atual: str = "",
) -> list[tuple[datetime, datetime]]:
    """Monta [início, fim) enquanto o substatus está em `alvos`."""
    saida: list[tuple[datetime, datetime]] = []
    if not eventos:
        if sub_atual in alvos and inicio_fallback and inicio_fallback < agora:
            saida.append((inicio_fallback, agora))
        return saida
    atual_sub: Optional[str] = None
    atual_ini: Optional[datetime] = None
    for quando, sub in eventos:
        if atual_sub in alvos and atual_ini is not None and atual_ini < quando:
            saida.append((atual_ini, quando))
        atual_sub = sub
        atual_ini = quando
    if atual_sub in alvos and atual_ini is not None and atual_ini < agora:
        saida.append((atual_ini, agora))
    return saida


def _max_por_hora(
    intervalos: Iterable[tuple[datetime, datetime]],
    dia: datetime,
) -> list[int]:
    dia0 = dia.replace(hour=0, minute=0, second=0, microsecond=0)
    max_h = [0] * 24
    clips: list[tuple[datetime, datetime]] = []
    dia1 = dia0 + timedelta(days=1)
    for ini, fim in intervalos:
        a = max(ini, dia0)
        b = min(fim, dia1)
        if a < b:
            clips.append((a, b))
    for h in range(24):
        w0 = dia0 + timedelta(hours=h)
        w1 = w0 + timedelta(hours=1)
        eventos: list[tuple[datetime, int]] = []
        ativos = 0
        for a, b in clips:
            if b <= w0 or a >= w1:
                continue
            if a <= w0 < b:
                ativos += 1
            if w0 < a < w1:
                eventos.append((a, 1))
            if w0 < b < w1:
                eventos.append((b, -1))
        eventos.sort(key=lambda x: (x[0], x[1]))
        cur = ativos
        melhor = cur
        for _t, delta in eventos:
            cur += delta
            if cur > melhor:
                melhor = cur
        max_h[h] = melhor
    return max_h


def top_picos(
    intervalos: Iterable[tuple[datetime, datetime]],
    dia: datetime,
    *,
    top: int = 3,
) -> list[PicoHora]:
    n = max(1, min(24, int(top)))
    max_h = _max_por_hora(intervalos, dia)
    ranking = sorted(
        ((h, c) for h, c in enumerate(max_h) if c > 0),
        key=lambda x: (-x[1], x[0]),
    )
    return [PicoHora(hora_ini=h, max_simultaneos=c) for h, c in ranking[:n]]


def montar_picos_projeto(
    projeto: str,
    intervalos_atendimento: Sequence[tuple[datetime, datetime]],
    intervalos_espera: Sequence[tuple[datetime, datetime]],
    dia: datetime,
    *,
    top: int = 3,
    equipe_hora: Sequence[EquipeHora] | None = None,
) -> PicosProjeto:
    picos_atend = top_picos(intervalos_atendimento, dia, top=top)
    picos_espera = top_picos(intervalos_espera, dia, top=top)
    if equipe_hora:
        picos_atend = preencher_equipe_picos(picos_atend, equipe_hora=equipe_hora)
        picos_espera = preencher_equipe_picos(picos_espera, equipe_hora=equipe_hora)
    return PicosProjeto(
        projeto=projeto,
        atendimento=picos_atend,
        espera=picos_espera,
    )
