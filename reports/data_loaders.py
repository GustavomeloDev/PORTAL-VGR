"""Carga de dados para relatórios SUPERVISORES (SQL parametrizado)."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from core.reports.analistas_disponiveis import (
    AnalistaDisponivel,
    filtrar_analistas_disponiveis,
)
from core.reports.env_config import blacklist_analistas_fila, env_int
from core.reports.fila_sem_analista import (
    FilaEsperaItem,
    as_datetime,
    espera_desde,
    filtrar_fila_atual,
    itens_final_do_log,
    sem_analista_config,
)
from core.reports.kpi_macro import SUB_FILA_REMOTA
from core.reports.picos_hora import (
    EquipeHora,
    PicosDia,
    SUBS_EM_ATENDIMENTO,
    SUBS_ESPERA_ANALISTA,
    equipe_por_hora_do_dia,
    intervalos_nos_alvos,
    montar_picos_projeto,
)
from core.reports.kpi_macro import _analista, segundos_hhmmss

logger = logging.getLogger(__name__)

_SQL_FUST_ATEND = (
    "SELECT a.id_atendimentos, a.data_atendimentos, a.status_atendimentos, "
    "a.substatus_atendimentos, a.analista_configuracao_atendimentos, "
    "a.analista_atuante_atendimentos, a.horario_inicio_atendimentos, "
    "a.horario_finalizacao_atendimentos, a.parada_atendimentos, a.id_escola_atendimentos, "
    "e.inep_escolas, e.nome_escolas, e.municipio_escolas, e.uf_escolas, "
    "e.data_agendamento_escolas, a.ultima_data_evento_especial_atendimentos "
    "FROM atendimentos a "
    "JOIN escolas e ON a.id_escola_atendimentos = e.id_escolas "
    "WHERE "
    "  DATE(a.data_atendimentos) BETWEEN %s AND %s "
    "  OR ("
    "    a.ultima_data_evento_especial_atendimentos IS NOT NULL "
    "    AND DATE(a.ultima_data_evento_especial_atendimentos) BETWEEN %s AND %s"
    "  )"
)

_SQL_FILA_FUST = (
    "SELECT a.id_atendimentos, e.inep_escolas, e.nome_escolas, "
    "e.municipio_escolas, e.uf_escolas, "
    "a.analista_configuracao_atendimentos, a.horario_inicio_atendimentos, "
    "(SELECT MAX(s.alterado_em_log) FROM atendimentos_status_log s "
    " WHERE s.id_atendimentos_log = a.id_atendimentos "
    " AND s.tipo_campo_log = 'substatus' "
    " AND s.valor_novo_log = %s) AS entrou_em "
    "FROM atendimentos a "
    "JOIN escolas e ON a.id_escola_atendimentos = e.id_escolas "
    "WHERE a.substatus_atendimentos = %s "
    "AND TRIM(IFNULL(a.analista_configuracao_atendimentos, '')) = ''"
)

_SQL_FILA_PRODESP = (
    "SELECT a.id_atendimentos, u.id_vgr_unidades, u.nome_unidades, "
    "u.municipio_unidades, u.estado_unidades, u.acronimo_unidades, "
    "a.analista_configuracao_atendimentos, a.horario_inicio_atendimentos, "
    "(SELECT MAX(s.alterado_em_log) FROM atendimentos_status_log s "
    " WHERE s.id_atendimentos_log = a.id_atendimentos "
    " AND s.tipo_campo_log = 'substatus' "
    " AND s.valor_novo_log = %s) AS entrou_em "
    "FROM atendimentos a "
    "JOIN unidades u ON u.id_unidades = a.id_unidades_atendimentos "
    "WHERE a.substatus_atendimentos = %s "
    "AND TRIM(IFNULL(a.analista_configuracao_atendimentos, '')) = ''"
)

_SQL_LOG_SUB = (
    "SELECT valor_novo_log, alterado_em_log "
    "FROM atendimentos_status_log "
    "WHERE id_atendimentos_log = %s AND tipo_campo_log = 'substatus' "
    "ORDER BY alterado_em_log ASC, id_log_atendimentos_status ASC"
)

_SQL_CANDIDATOS_FINAL_FUST = (
    "SELECT a.id_atendimentos, e.inep_escolas, e.nome_escolas, "
    "e.municipio_escolas, e.uf_escolas, a.analista_configuracao_atendimentos "
    "FROM atendimentos a "
    "JOIN escolas e ON a.id_escola_atendimentos = e.id_escolas "
    "WHERE DATE(a.data_atendimentos) = %s "
    "AND TRIM(IFNULL(a.analista_configuracao_atendimentos, '')) <> ''"
)

_SQL_CANDIDATOS_FINAL_PRODESP = (
    "SELECT a.id_atendimentos, u.id_vgr_unidades, u.nome_unidades, "
    "u.municipio_unidades, u.estado_unidades, u.acronimo_unidades, "
    "a.analista_configuracao_atendimentos "
    "FROM atendimentos a "
    "JOIN unidades u ON u.id_unidades = a.id_unidades_atendimentos "
    "WHERE DATE(a.data_atendimentos) = %s "
    "AND TRIM(IFNULL(a.analista_configuracao_atendimentos, '')) <> ''"
)

_SQL_PICOS_DIA = (
    "SELECT a.id_atendimentos, a.horario_inicio_atendimentos, a.substatus_atendimentos "
    "FROM atendimentos a "
    "WHERE DATE(a.data_atendimentos) = %s"
)

_SQL_LOG_SUB_IDS = (
    "SELECT id_atendimentos_log, valor_novo_log, alterado_em_log "
    "FROM atendimentos_status_log "
    "WHERE tipo_campo_log = 'substatus' "
    "AND id_atendimentos_log IN ({ids}) "
    "ORDER BY id_atendimentos_log ASC, alterado_em_log ASC, id_log_atendimentos_status ASC"
)


def _fechar(cursor, conn) -> None:
    if cursor is not None:
        try:
            cursor.close()
        except Exception:
            pass
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def carregar_rows_prodesp(start_date: str, end_date: str) -> list[dict[str, Any]]:
    from prodesp.app import (
        _prodesp_carregar_dados_dashboard_periodo,
        get_db_connection_long_running,
    )

    conn = get_db_connection_long_running()
    cursor = None
    try:
        rows, _scheduled, cursor, _conn, _own = _prodesp_carregar_dados_dashboard_periodo(
            start_date, end_date, conn=conn
        )
        return list(rows or [])
    finally:
        _fechar(cursor, conn)


def carregar_rows_fust(start_date: str, end_date: str) -> list[dict[str, Any]]:
    from fust.app import get_db_connection, processar_atendimentos_para_dashboard
    from fust.fust.agendamento_escola import sql_escolas_agendadas_sem_atendimento

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    rows: list[dict[str, Any]] = []
    try:
        cursor.execute(_SQL_FUST_ATEND, (start_date, end_date, start_date, end_date))
        for row in cursor.fetchall() or []:
            row["id_atendimento"] = row.get("id_atendimentos")
            # Espelha o mesmo mapeamento que a API dashboard FUST usa (api_dashboard_data L1527-L1530)
            # antes de chamar processar_atendimentos_para_dashboard → calcula tempo_em_segundos.
            row["data_atendimento"] = row.get("data_atendimentos")
            row["horario_inicio"] = row.get("horario_inicio_atendimentos")
            row["horario_finalizacao"] = row.get("horario_finalizacao_atendimentos")
            row["parada"] = row.get("parada_atendimentos")
            rows.append(row)
        # Popula tempo_em_segundos em cada linha usando a mesma lógica oficial do dashboard web FUST
        if rows:
            try:
                processar_atendimentos_para_dashboard(rows)
            except Exception:
                logger.warning(
                    "supervisores - processar_atendimentos_para_dashboard falhou no FUST; "
                    "tempo_em_segundos será None em linhas sem cálculo fallback manual",
                    exc_info=True,
                )
        # Fallback manual: linhas que ainda tem tempo_em_segundos None mas tem horario inicio/final datetime calcula bruto
        for r in rows:
            if r.get("tempo_em_segundos") is None:
                _fallback_preencher_tempo_fust(r)
        cursor.execute(sql_escolas_agendadas_sem_atendimento(), (start_date, end_date))
        for row in cursor.fetchall() or []:
            rows.append(
                {
                    "id_atendimento": None,
                    "status_atendimentos": "Agendado",
                    "substatus_atendimentos": "",
                    "inep_escolas": row.get("inep"),
                    "nome_escolas": row.get("nome"),
                }
            )
        return rows
    except Exception:
        logger.exception("supervisores - falha ao carregar dashboard FUST")
        return rows
    finally:
        _fechar(cursor, conn)


def _fallback_preencher_tempo_fust(row: dict[str, Any]) -> None:
    """Caso o processar_atendimentos_para_dashboard não consiga rodar (ex: falta Flask app context parser
    datas), faz um cálculo manual via timedelta para garantir que tempo_em_segundos exista.

    Mantém o padrão: (horario_final - horario_inicio) - parada, tudo em segundos. Não leva em conta
    dia seguinte (o processar_atendimentos_para_dashboard trata isso e é o caminho feliz).
    """
    from datetime import datetime, timedelta
    try:
        data = row.get("data_atendimentos") or row.get("data_atendimento")
        hi = row.get("horario_inicio_atendimentos") or row.get("horario_inicio")
        hf = row.get("horario_finalizacao_atendimentos") or row.get("horario_finalizacao")
        if not (data and hi and hf):
            return
        if isinstance(hi, timedelta):
            hi_sec = int(hi.total_seconds())
            hh, mm, ss = hi_sec // 3600, (hi_sec % 3600) // 60, hi_sec % 60
            hi_obj = (dt := datetime.min + hi).time() if hasattr(datetime, "min") else None
        else:
            hi_obj = hi
        if isinstance(hf, timedelta):
            hf_sec = int(hf.total_seconds())
            hh, mm, ss = hf_sec // 3600, (hf_sec % 3600) // 60, hf_sec % 60
            hf_obj = (datetime.min + hf).time() if hasattr(datetime, "min") else None
        else:
            hf_obj = hf
        parada = row.get("parada_atendimentos") or row.get("parada")
        parada_sec = int(parada.total_seconds()) if isinstance(parada, timedelta) else int(parada or 0)
        if isinstance(data, datetime):
            data_d = data.date()
        elif hasattr(data, "date"):
            data_d = data.date()
        else:
            return
        if not (hasattr(hi_obj, "hour") and hasattr(hf_obj, "hour")):
            return
        dt_i = datetime.combine(data_d, hi_obj)
        dt_f = datetime.combine(data_d, hf_obj)
        if dt_f < dt_i:
            dt_f += timedelta(days=1)
        bruto = int((dt_f - dt_i).total_seconds())
        row["tempo_em_segundos"] = max(0, bruto - parada_sec)
    except Exception:
        pass


def _item_fila_row(
    *,
    projeto: str,
    row: dict[str, Any],
    chave: str,
    unidade: str,
    municipio: str,
    uf: str,
    agora: Optional[datetime] = None,
) -> Optional[FilaEsperaItem]:
    if not sem_analista_config(row):
        return None
    try:
        id_att = int(row.get("id_atendimentos") or 0)
    except (TypeError, ValueError):
        return None
    if id_att <= 0:
        return None
    entrou = as_datetime(row.get("entrou_em")) or as_datetime(row.get("horario_inicio_atendimentos"))
    espera = espera_desde(entrou, agora)
    return FilaEsperaItem(
        projeto=projeto,
        id_atendimento=id_att,
        chave=chave,
        unidade=unidade,
        municipio=municipio,
        uf=uf,
        entrou_em=entrou,
        espera_seg=espera,
        analista="",
    )


def carregar_fila_atual(*, minutos_min: int = 30) -> list[FilaEsperaItem]:
    itens: list[FilaEsperaItem] = []
    itens.extend(_fila_fust_atual())
    itens.extend(_fila_prodesp_atual())
    return filtrar_fila_atual(itens, minutos_min=minutos_min)


def _fila_fust_atual() -> list[FilaEsperaItem]:
    from fust.app import get_db_connection

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    saida: list[FilaEsperaItem] = []
    try:
        cursor.execute(_SQL_FILA_FUST, (SUB_FILA_REMOTA, SUB_FILA_REMOTA))
        for row in cursor.fetchall() or []:
            item = _item_fila_row(
                projeto="FUST",
                row=row,
                chave=str(row.get("inep_escolas") or ""),
                unidade=str(row.get("nome_escolas") or ""),
                municipio=str(row.get("municipio_escolas") or ""),
                uf=str(row.get("uf_escolas") or ""),
            )
            if item:
                saida.append(item)
    except Exception:
        logger.exception("supervisores - falha ao ler fila FUST")
    finally:
        _fechar(cursor, conn)
    return saida


def _fila_prodesp_atual() -> list[FilaEsperaItem]:
    from prodesp.app import get_db_connection_long_running

    conn = get_db_connection_long_running()
    cursor = conn.cursor(dictionary=True)
    saida: list[FilaEsperaItem] = []
    try:
        cursor.execute(_SQL_FILA_PRODESP, (SUB_FILA_REMOTA, SUB_FILA_REMOTA))
        for row in cursor.fetchall() or []:
            acr = str(row.get("acronimo_unidades") or "").strip()
            nome = str(row.get("nome_unidades") or "").strip()
            unidade = f"{acr} — {nome}" if acr and nome else (acr or nome)
            item = _item_fila_row(
                projeto="PRODESP",
                row=row,
                chave=str(row.get("id_vgr_unidades") or ""),
                unidade=unidade,
                municipio=str(row.get("municipio_unidades") or ""),
                uf=str(row.get("estado_unidades") or ""),
            )
            if item:
                saida.append(item)
    except Exception:
        logger.exception("supervisores - falha ao ler fila PRODESP")
    finally:
        _fechar(cursor, conn)
    return saida


def carregar_fila_final(dia_iso: str, *, minutos_min: int = 30) -> list[FilaEsperaItem]:
    saida: list[FilaEsperaItem] = []
    saida.extend(_final_projeto("FUST", dia_iso, minutos_min))
    saida.extend(_final_projeto("PRODESP", dia_iso, minutos_min))
    saida.sort(key=lambda x: x.espera_seg, reverse=True)
    return saida


def _final_projeto(projeto: str, dia_iso: str, minutos_min: int) -> list[FilaEsperaItem]:
    if projeto == "FUST":
        from fust.app import get_db_connection

        conn = get_db_connection()
        sql = _SQL_CANDIDATOS_FINAL_FUST
    else:
        from prodesp.app import get_db_connection_long_running

        conn = get_db_connection_long_running()
        sql = _SQL_CANDIDATOS_FINAL_PRODESP
    cursor = conn.cursor(dictionary=True)
    saida: list[FilaEsperaItem] = []
    try:
        cursor.execute(sql, (dia_iso,))
        rows = list(cursor.fetchall() or [])
        for row in rows:
            try:
                id_att = int(row.get("id_atendimentos") or 0)
            except (TypeError, ValueError):
                continue
            if id_att <= 0:
                continue
            cursor.execute(_SQL_LOG_SUB, (id_att,))
            eventos = list(cursor.fetchall() or [])
            if projeto == "FUST":
                chave = str(row.get("inep_escolas") or "")
                unidade = str(row.get("nome_escolas") or "")
                municipio = str(row.get("municipio_escolas") or "")
                uf = str(row.get("uf_escolas") or "")
            else:
                acr = str(row.get("acronimo_unidades") or "").strip()
                nome = str(row.get("nome_unidades") or "").strip()
                chave = str(row.get("id_vgr_unidades") or "")
                unidade = f"{acr} — {nome}" if acr and nome else (acr or nome)
                municipio = str(row.get("municipio_unidades") or "")
                uf = str(row.get("estado_unidades") or "")
            saida.extend(
                itens_final_do_log(
                    projeto=projeto,
                    id_atendimento=id_att,
                    chave=chave,
                    unidade=unidade,
                    municipio=municipio,
                    uf=uf,
                    analista_atual=str(row.get("analista_configuracao_atendimentos") or "").strip(),
                    eventos=eventos,
                    minutos_min=minutos_min,
                )
            )
    except Exception:
        logger.exception("supervisores - falha no report final da fila %s", projeto)
    finally:
        _fechar(cursor, conn)
    return saida


def carregar_analistas_disponiveis() -> list[AnalistaDisponivel]:
    """Espelha status/plataforma do portal e finalizados de hoje; só IMPLANTAÇÃO principal."""
    from datetime import datetime as _dt

    import pytz

    from login.models import AtendimentoGlobal, User
    from login.portal_access_config import DEPT_IMPLANTACAO

    try:
        hoje = _dt.now(pytz.timezone("America/Sao_Paulo")).date().isoformat()
        rows = User.get_all_kpi_data_supervisao()
        ativos_ids: set[int] = set()
        carregou_cadastro = False
        for u in User.all(apenas_ativos=True):
            carregou_cadastro = True
            try:
                uid = int(u.id_user)
            except (TypeError, ValueError):
                continue
            try:
                eh_admin = int(getattr(u, "admin_user", 0) or 0) == 1
            except (TypeError, ValueError):
                eh_admin = False
            if eh_admin:
                continue
            ativos_ids.add(uid)
        if carregou_cadastro:
            filtrados = []
            for row in rows:
                try:
                    uid = int(row.get("id_user") or 0)
                except (TypeError, ValueError):
                    uid = 0
                if uid and uid in ativos_ids:
                    filtrados.append(row)
            rows = filtrados
        contagens = AtendimentoGlobal.contar_atividades_por_analista(
            projetos=None,
            data_inicio=hoje,
            data_fim=hoje,
        )
        return filtrar_analistas_disponiveis(
            rows, contagens, blacklist_analistas_fila(), dept_principal=DEPT_IMPLANTACAO
        )
    except Exception:
        logger.exception("supervisores - falha ao listar analistas disponíveis")
        return []


def _eventos_substatus_por_id(cursor, ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {i: [] for i in ids}
    chunk = 150
    for i in range(0, len(ids), chunk):
        parte = ids[i : i + chunk]
        placeholders = ",".join(["%s"] * len(parte))
        cursor.execute(_SQL_LOG_SUB_IDS.format(ids=placeholders), tuple(parte))
        for row in cursor.fetchall() or []:
            try:
                id_att = int(row.get("id_atendimentos_log") or 0)
            except (TypeError, ValueError):
                continue
            if id_att in out:
                out[id_att].append(row)
    return out


def _intervalos_projeto_dia(projeto: str, dia_iso: str, agora: datetime):
    if projeto == "FUST":
        from fust.app import get_db_connection

        conn = get_db_connection()
    else:
        from prodesp.app import get_db_connection_long_running

        conn = get_db_connection_long_running()
    cursor = conn.cursor(dictionary=True)
    atend: list[tuple[datetime, datetime]] = []
    espera: list[tuple[datetime, datetime]] = []
    try:
        cursor.execute(_SQL_PICOS_DIA, (dia_iso,))
        rows = list(cursor.fetchall() or [])
        ids: list[int] = []
        meta: dict[int, dict[str, Any]] = {}
        for row in rows:
            try:
                id_att = int(row.get("id_atendimentos") or 0)
            except (TypeError, ValueError):
                continue
            if id_att <= 0:
                continue
            ids.append(id_att)
            meta[id_att] = row
        logs_map = _eventos_substatus_por_id(cursor, ids) if ids else {}
        for id_att, row in meta.items():
            eventos_dt: list[tuple[datetime, str]] = []
            for ev in logs_map.get(id_att) or []:
                quando = as_datetime(ev.get("alterado_em_log"))
                sub = str(ev.get("valor_novo_log") or "").strip()
                if quando and sub:
                    eventos_dt.append((quando, sub))
            eventos_dt.sort(key=lambda x: x[0])
            inicio = as_datetime(row.get("horario_inicio_atendimentos"))
            sub_atual = str(row.get("substatus_atendimentos") or "").strip()
            atend.extend(
                intervalos_nos_alvos(
                    eventos_dt,
                    alvos=SUBS_EM_ATENDIMENTO,
                    agora=agora,
                    inicio_fallback=inicio,
                    sub_atual=sub_atual,
                )
            )
            espera.extend(
                intervalos_nos_alvos(
                    eventos_dt,
                    alvos=SUBS_ESPERA_ANALISTA,
                    agora=agora,
                    inicio_fallback=inicio,
                    sub_atual=sub_atual,
                )
            )
    except Exception:
        logger.exception("supervisores - falha ao montar picos %s", projeto)
    finally:
        _fechar(cursor, conn)
    return atend, espera


def carregar_picos_do_dia(
    dia_iso: str,
    *,
    agora: Optional[datetime] = None,
    rows_fust: Optional[list[dict[str, Any]]] = None,
    rows_prodesp: Optional[list[dict[str, Any]]] = None,
    analistas_disponiveis_ids: Optional[list[Any]] = None,
) -> PicosDia:
    from datetime import datetime as _dt, timedelta as _td

    import pytz

    tz = pytz.timezone("America/Sao_Paulo")
    now = agora or _dt.now(tz)
    try:
        dia = tz.localize(_dt.strptime(dia_iso[:10], "%Y-%m-%d"))
    except (TypeError, ValueError):
        dia = now.replace(hour=0, minute=0, second=0, microsecond=0)
    top = env_int("SUPERVISORES_FILA_PICO_TOP", 3)
    atend_f, espera_f = _intervalos_projeto_dia("FUST", dia_iso, now)
    atend_p, espera_p = _intervalos_projeto_dia("PRODESP", dia_iso, now)

    equipe_hora: Optional[list[EquipeHora]] = None
    if analistas_disponiveis_ids is not None and rows_fust is not None and rows_prodesp is not None:
        try:
            atuando_por_hora: list[set[str]] = [set() for _ in range(24)]
            dia0 = dia.replace(hour=0, minute=0, second=0, microsecond=0)
            for projeto, rows in (("FUST", rows_fust or []), ("PRODESP", rows_prodesp or [])):
                for r in rows:
                    nome = _analista(r)
                    if not nome:
                        continue
                    hi = r.get("horario_inicio_atendimentos")
                    hf = r.get("horario_finalizacao_atendimentos") or r.get("parada_atendimentos")
                    if hi is None:
                        continue
                    try:
                        seg_ini = 0
                        if isinstance(hi, _td):
                            seg_ini = int(hi.total_seconds())
                        else:
                            s = str(hi)
                            if len(s) >= 8:
                                seg_ini = int(s[0:2]) * 3600 + int(s[3:5]) * 60 + int(s[6:8])
                        seg_fim = 0
                        if isinstance(hf, _td):
                            seg_fim = int(hf.total_seconds())
                        elif hf is not None:
                            s = str(hf)
                            if len(s) >= 8:
                                seg_fim = int(s[0:2]) * 3600 + int(s[3:5]) * 60 + int(s[6:8])
                        if seg_fim <= seg_ini:
                            seg_fim = seg_ini + 1800
                        for h in range(24):
                            w_ini = h * 3600
                            w_fim = (h + 1) * 3600
                            if seg_ini < w_fim and seg_fim > w_ini:
                                atuando_por_hora[h].add(nome)
                    except (TypeError, ValueError, IndexError):
                        continue
            equipe_hora = equipe_por_hora_do_dia(
                analistas_disponiveis_ids,
                atuando_por_hora=atuando_por_hora,
                dia=dia,
            )
        except Exception:
            logger.exception("supervisores - falha ao montar equipe_hora para picos")
            equipe_hora = None

    return PicosDia(
        fust=montar_picos_projeto("FUST", atend_f, espera_f, dia, top=top, equipe_hora=equipe_hora),
        prodesp=montar_picos_projeto("PRODESP", atend_p, espera_p, dia, top=top, equipe_hora=equipe_hora),
        geral=montar_picos_projeto(
            "GERAL",
            list(atend_f) + list(atend_p),
            list(espera_f) + list(espera_p),
            dia,
            top=top,
            equipe_hora=equipe_hora,
        ),
    )


def carregar_kpis_resumo_supervisao_dia(
    dia_iso: str,
) -> dict[str, dict[str, Any]]:
    """Carrega KPIs do painel supervisão para FUST e PRODESP.

    Usa `AtendimentoGlobal.resumo_supervisao` como fonte de verdade para os
    KPIs novos do painel (Em Configuração Remota, Aguardando/Em Caderno de
    Teste e Tempo Médio de atendimentos concluídos com duração > 0s).
    """
    resultado: dict[str, dict[str, Any]] = {
        "FUST": {
            "tempo_medio_seg": None,
            "tempo_medio_total_seg": None,
            "em_config_remota_cnt": 0,
            "aguardando_caderno_teste_cnt": 0,
            "aguardando_caderno_cnt": 0,
            "em_caderno_cnt": 0,
            "aguardando_config_mpls_cnt": 0,
            "em_config_mpls_cnt": 0,
        },
        "PRODESP": {
            "tempo_medio_seg": None,
            "tempo_medio_total_seg": None,
            "em_config_remota_cnt": 0,
            "aguardando_caderno_teste_cnt": 0,
            "aguardando_caderno_cnt": 0,
            "em_caderno_cnt": 0,
            "aguardando_config_mpls_cnt": 0,
            "em_config_mpls_cnt": 0,
        },
    }
    try:
        from login.models import AtendimentoGlobal
    except Exception:
        logger.exception("supervisores - não foi possível importar AtendimentoGlobal")
        return resultado
    for projeto in ("FUST", "PRODESP"):
        try:
            resumo = AtendimentoGlobal.resumo_supervisao(
                projetos=[projeto],
                data_inicio=dia_iso[:10],
                data_fim=dia_iso[:10],
            ) or {}
            kpi = dict(resumo.get("kpi") or {})
            resultado[projeto] = {
                "tempo_medio_seg": kpi.get("tempo_medio_seg"),
                "tempo_medio_total_seg": kpi.get("tempo_medio_total_seg"),
                "em_config_remota_cnt": int(kpi.get("em_config_remota_cnt") or 0),
                "aguardando_caderno_teste_cnt": int(
                    kpi.get("aguardando_caderno_teste_cnt") or 0
                ),
                "aguardando_caderno_cnt": int(kpi.get("aguardando_caderno_cnt") or 0),
                "em_caderno_cnt": int(kpi.get("em_caderno_cnt") or 0),
                "aguardando_config_mpls_cnt": int(kpi.get("aguardando_config_mpls_cnt") or 0),
                "em_config_mpls_cnt": int(kpi.get("em_config_mpls_cnt") or 0),
            }
        except Exception:
            logger.exception(
                "supervisores - falha ao carregar resumo supervisão %s em %s",
                projeto,
                dia_iso,
            )
    return resultado
