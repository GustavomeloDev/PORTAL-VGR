"""
Orquestração: permissões, carga de dados, coleta SSH e geração do caderno PRODESP.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from prodesp.prodesp.caderno.caderno_template_map import CADERNO_MODELO_SOLUCAO_VALOR
from prodesp.prodesp.caderno.fgt_admin_cleanup import extrair_resumo_limpeza_admin_coleta
from prodesp.prodesp.caderno.fgt_ssh_collector import (
    coletar_logs_fgt,
    extrair_bloco_coleta_fgt,
    sanitize_logs_atendimento_for_db,
    substituir_bloco_coleta_fgt,
)
from prodesp.prodesp.caderno.gerador_caderno_prodesp import CadernoGeracaoError, gerar_caderno_prodesp
from prodesp.prodesp.caderno.fgt_cert_exporter import _sanitizar_motivo_historico
from prodesp.prodesp.db_field_limits import LOGS_ATENDIMENTOS_MAX, truncate_mysql_text_field
from prodesp.prodesp.historico import registrar_log

SUBSTATUS_CADERNO = "Em Caderno de Teste"

_CAMPO_HISTORICO_COLETA = "Coleta de Logs FGT"
_CAMPO_HISTORICO_GERACAO = "Geração de Caderno de Teste"

_HISTORICO_COLETA_TEXTO_MAX = 8000

_MSG_CADERNO_SHAREPOINT = " Uma cópia foi salva no SharePoint da PRODESP."

_CAMPOS_QUESTIONARIO_OBRIGATORIOS: tuple[tuple[str, str], ...] = (
    ("dhcp_server", "Possui DHCP-Server?"),
    ("dhcp_relay", "Possui DHCP-Relay?"),
    ("vlan", "Possui VLAN?"),
    ("multi_ip_lan", "Possui mais de um IP na LAN?"),
    ("voip_tipo", "VOIP — CPE ou FGT?"),
)


def _registrar_historico_caderno(
    conn,
    id_atendimento: int,
    campo: str,
    texto: str,
    *,
    automatico: bool = False,
) -> None:
    if automatico:
        prefixo = "Ação automática do portal."
        texto = f"{prefixo}\n\n{texto}" if texto else prefixo
    registrar_log(
        conn,
        "atendimentos",
        id_atendimento,
        campo,
        "",
        texto,
        "INSERT",
    )


def _truncar_texto_historico_coleta(texto: str) -> str:
    t = (texto or "").strip()
    if len(t) <= _HISTORICO_COLETA_TEXTO_MAX:
        return t
    return t[: _HISTORICO_COLETA_TEXTO_MAX - 16].rstrip() + "\n… [truncado]"


def _historico_coleta_sucesso(
    *,
    hostname: str,
    acronimo: str,
    elapsed_seconds: float,
    commands_run: int,
    log_chars: int,
    parcial: bool,
    resumo_limpeza_admin: str = "",
    avisos: Optional[list[str]] = None,
) -> str:
    titulo = (
        "Coleta de logs FGT concluída com ressalvas."
        if parcial
        else "Coleta de logs FGT concluída com sucesso."
    )
    lines = [titulo]
    if elapsed_seconds:
        lines.append(f"Tempo: {elapsed_seconds}s")
    if hostname:
        lines.append(f"Hostname: {hostname}")
    if acronimo:
        lines.append(f"Secretaria: {acronimo}")
    if commands_run:
        lines.append(f"Comandos executados: {commands_run}")
    if log_chars:
        lines.append(f"Tamanho do log gravado: {log_chars} caracteres")
    if (resumo_limpeza_admin or "").strip():
        lines.extend(["", resumo_limpeza_admin.strip()])
    if avisos:
        aviso_txt = "; ".join(str(a).strip() for a in avisos if a and str(a).strip())
        if aviso_txt:
            lines.extend(["", f"Avisos: {_sanitizar_motivo_historico(aviso_txt, max_len=1200)}"])
    return _truncar_texto_historico_coleta("\n".join(lines).strip())


def _historico_coleta_falha(
    *,
    hostname: str,
    acronimo: str,
    motivo: str,
    resumo_limpeza_admin: str = "",
) -> str:
    lines = ["Falha na coleta de logs FGT."]
    if hostname:
        lines.append(f"Hostname: {hostname}")
    if acronimo:
        lines.append(f"Secretaria: {acronimo}")
    lines.extend(["", f"Motivo: {_sanitizar_motivo_historico(motivo)}"])
    if (resumo_limpeza_admin or "").strip():
        lines.extend(["", resumo_limpeza_admin.strip()])
    return _truncar_texto_historico_coleta("\n".join(lines).strip())


def _historico_geracao_sucesso(
    *,
    filename: str,
    hostname: str,
    acronimo: str,
    copia_rede: bool,
) -> str:
    lines = ["Caderno de teste gerado com sucesso."]
    if filename:
        lines.append(f"Arquivo: {filename}")
    if hostname:
        lines.append(f"Hostname: {hostname}")
    if acronimo:
        lines.append(f"Secretaria: {acronimo}")
    lines.append(f"Cópia SharePoint/rede: {'sim' if copia_rede else 'não'}")
    return "\n".join(lines).strip()


def _historico_geracao_falha(*, hostname: str, acronimo: str, motivo: str) -> str:
    lines = ["Falha na geração do caderno de teste."]
    if hostname:
        lines.append(f"Hostname: {hostname}")
    if acronimo:
        lines.append(f"Secretaria: {acronimo}")
    lines.extend(["", f"Motivo: {_sanitizar_motivo_historico(motivo)}"])
    return "\n".join(lines).strip()


def mensagem_sucesso_geracao_caderno(*, copia_rede: bool) -> str:
    msg = "Caderno gerado com sucesso."
    if copia_rede:
        msg += _MSG_CADERNO_SHAREPOINT
    return msg


def caminhos_download_caderno(filename: str, acronimo: str = "") -> list[str]:
    """Ordem: cópia local do portal, depois pasta SharePoint/rede por acrônimo."""
    from prodesp.config_paths import iter_pastas_rede_caderno
    from prodesp.prodesp.caderno.gerador_caderno_prodesp import resolve_gerados_dir

    def _variantes(nome: str) -> list[str]:
        base, ext = os.path.splitext(nome)
        if not base:
            return [nome]
        ext = ext.lower()
        if ext in (".xlsx", ".xlsm"):
            alt = ".xlsm" if ext == ".xlsx" else ".xlsx"
            return [nome, f"{base}{alt}"]
        return [nome]

    paths: list[str] = []
    for nome in _variantes(filename):
        local = os.path.join(resolve_gerados_dir(), nome)
        if local not in paths:
            paths.append(local)
    for rede_dir in iter_pastas_rede_caderno((acronimo or "").strip()):
        for nome in _variantes(filename):
            rede = os.path.join(rede_dir, nome)
            if rede not in paths:
                paths.append(rede)
    return paths


def mimetype_caderno(filename: str) -> str:
    if (filename or "").lower().endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/vnd.ms-excel.sheet.macroEnabled.12"


def ler_bytes_arquivo_caderno(path: str, *, retries: int = 6) -> bytes:
    """Lê .xlsm com retry — Excel/OneDrive podem manter lock breve após geração."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            with open(path, "rb") as handle:
                return handle.read()
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.35 * (attempt + 1))
    if last_exc:
        raise last_exc
    raise FileNotFoundError(path)


def validar_questionario_obrigatorio(questionario: dict) -> tuple[bool, str]:
    for campo, rotulo in _CAMPOS_QUESTIONARIO_OBRIGATORIOS:
        val = (questionario.get(campo) or "").strip()
        if not val:
            return False, f"Responda: {rotulo}"
    return True, ""


def validar_status_testes(status_testes: dict) -> tuple[bool, str]:
    """Valida status informados pelo analista (linhas 40–49)."""
    from prodesp.prodesp.caderno.caderno_template_map import CADERNO_STATUS_OPCOES, CADERNO_TESTES_ANALISTA_ROWS

    permitidos = set(CADERNO_STATUS_OPCOES)
    normalizado: dict[int, str] = {}
    for key, val in (status_testes or {}).items():
        try:
            row = int(key)
        except (TypeError, ValueError):
            return False, "Status de teste inválido."
        st = (val or "").strip()
        if st not in permitidos:
            return False, "Status de teste inválido."
        normalizado[row] = st

    faltando = CADERNO_TESTES_ANALISTA_ROWS - set(normalizado.keys())
    if faltando:
        return False, "Informe o status de todos os testes (Bandwidth e testes Cliente)."
    return True, ""


def pode_acionar_caderno(user, row: dict, *, is_admin: bool) -> tuple[bool, str]:
    """Admin a qualquer momento; analista dono na etapa Em Caderno de Teste."""
    if is_admin:
        return True, ""
    sub = (row.get("substatus_atendimentos") or row.get("substatus") or "").strip()
    if sub != SUBSTATUS_CADERNO:
        return False, "Disponível na etapa «Em Caderno de Teste» ou para administradores."
    analista = (
        row.get("analista_caderno_teste_atendimentos")
        or row.get("analista_caderno_teste")
        or ""
    ).strip()
    nome = (getattr(user, "nome_user", None) or getattr(user, "nome", None) or "").strip()
    if analista and nome and analista.strip().lower() == str(nome).strip().lower():
        return True, ""
    from login.portal_access_config import DEPT_IMPLANTACAO, departamentos_do_usuario

    if DEPT_IMPLANTACAO in departamentos_do_usuario(user):
        return True, ""
    return False, "Sem permissão para esta ação no atendimento."


def _row_get(row: Any, key: str, default: str = "") -> str:
    if isinstance(row, dict):
        v = row.get(key, default)
    else:
        v = row[key] if key in row.keys() else default
    return (v or default) if v is not None else default


def carregar_contexto_atendimento(cursor, id_atendimento: int) -> Optional[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            a.id_atendimentos,
            a.substatus_atendimentos,
            a.analista_caderno_teste_atendimentos,
            a.logs_atendimentos,
            u.id_unidades,
            u.id_vgr_unidades,
            u.acronimo_unidades,
            u.nome_unidades,
            u.municipio_unidades,
            u.estado_unidades,
            u.hostname_unidades,
            u.loopback_vivo_unidades,
            u.id_intragov_unidades,
            u.ip_lan_01_unidades,
            u.mv_ip_lan_sec_unidades,
            u.ip_lan_transito_unidades
        FROM atendimentos a
        JOIN unidades u ON u.id_unidades = a.id_unidades_atendimentos
        WHERE a.id_atendimentos = %s
        LIMIT 1
        """,
        (id_atendimento,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    if hasattr(row, "keys"):
        base = dict(row)
    else:
        cols = [d[0] for d in cursor.description]
        base = dict(zip(cols, row))

    id_unidade = base.get("id_unidades")
    cursor.execute(
        """
        SELECT modelo_equipamentos, serial_equipamentos, versao_equipamentos, descricao_equipamentos
        FROM equipamentos
        WHERE id_unidades_equipamentos = %s
        ORDER BY id_equipamentos
        """,
        (id_unidade,),
    )
    eq_rows = cursor.fetchall()
    equipamentos = []
    for er in eq_rows:
        if hasattr(er, "keys"):
            equipamentos.append(dict(er))
        else:
            equipamentos.append(
                {
                    "modelo_equipamentos": er[0],
                    "serial_equipamentos": er[1],
                    "versao_equipamentos": er[2],
                    "descricao_equipamentos": er[3],
                }
            )

    cursor.execute(
        """
        SELECT id_vgr_links, designador_links, tipo_links, operadora_links, vlan_links,
               ip_wan_links, ip_gateway_links, ip_mascara_links, velocidade_links
        FROM links
        WHERE id_unidades_links = %s
        ORDER BY id_link
        """,
        (id_unidade,),
    )
    lk_rows = cursor.fetchall()
    links = []
    for lr in lk_rows:
        if hasattr(lr, "keys"):
            links.append(dict(lr))
        else:
            links.append(
                {
                    "id_vgr_links": lr[0],
                    "designador_links": lr[1],
                    "tipo_links": lr[2],
                    "operadora_links": lr[3],
                    "vlan_links": lr[4],
                    "ip_wan_links": lr[5],
                    "ip_gateway_links": lr[6],
                    "ip_mascara_links": lr[7],
                    "velocidade_links": lr[8],
                }
            )

    municipio = (base.get("municipio_unidades") or "").strip()
    estado = (base.get("estado_unidades") or "").strip()
    localidade = f"{municipio}/{estado}".strip("/") if municipio or estado else ""

    return {
        "atendimento": base,
        "unidade": {
            "id_vgr_unidades": base.get("id_vgr_unidades"),
            "acronimo_unidades": base.get("acronimo_unidades"),
            "nome_unidades": base.get("nome_unidades"),
            "site_name_unidades": base.get("nome_unidades"),
            "localidade_unidades": localidade,
            "topologia_unidades": "SD-WAN",
            "modelo_solucao_unidades": CADERNO_MODELO_SOLUCAO_VALOR,
            "hostname_unidades": base.get("hostname_unidades"),
            "loopback_vivo_unidades": base.get("loopback_vivo_unidades"),
            "id_intragov_unidades": base.get("id_intragov_unidades"),
            "ip_lan_01_unidades": base.get("ip_lan_01_unidades"),
            "mv_ip_lan_sec_unidades": base.get("mv_ip_lan_sec_unidades"),
            "ip_lan_transito_unidades": base.get("ip_lan_transito_unidades"),
        },
        "equipamentos": equipamentos,
        "links": links,
        "logs_atendimentos": base.get("logs_atendimentos") or "",
    }


def executar_coleta(
    cursor,
    conn,
    id_atendimento: int,
    *,
    registrar_auditoria: bool = True,
    automatico: bool = False,
) -> dict[str, Any]:
    ctx = carregar_contexto_atendimento(cursor, id_atendimento)
    if not ctx:
        return {"ok": False, "message": "Atendimento não encontrado."}

    unidade = ctx.get("unidade") or {}
    hostname = (unidade.get("hostname_unidades") or "").strip()
    acronimo = (unidade.get("acronimo_unidades") or "").strip()
    loopback = (unidade.get("loopback_vivo_unidades") or "").strip()
    if not loopback:
        msg = "Loopback Vivo não cadastrado na unidade."
        if registrar_auditoria:
            _registrar_historico_caderno(
                conn,
                id_atendimento,
                _CAMPO_HISTORICO_COLETA,
                _historico_coleta_falha(hostname=hostname, acronimo=acronimo, motivo=msg),
                automatico=automatico,
            )
            conn.commit()
        return {"ok": False, "message": msg}

    equipamentos = [
        {
            "serial": e.get("serial_equipamentos"),
            "modelo": e.get("modelo_equipamentos"),
        }
        for e in ctx["equipamentos"]
    ]
    modelo = (equipamentos[0].get("modelo") if equipamentos else "") or ""
    id_intragov = (unidade.get("id_intragov_unidades") or "").strip()

    t0 = time.time()
    result = coletar_logs_fgt(
        loopback,
        acronimo=acronimo,
        modelo=modelo,
        equipamentos=equipamentos or None,
        id_intragov=id_intragov,
    )
    elapsed = round(time.time() - t0, 1)
    if not result.logs_text and result.errors:
        msg = result.errors[0]
        payload = {
            "ok": False,
            "message": msg,
            "errors": result.errors,
            "elapsed_seconds": elapsed,
        }
        if registrar_auditoria:
            _registrar_historico_caderno(
                conn,
                id_atendimento,
                _CAMPO_HISTORICO_COLETA,
                _historico_coleta_falha(hostname=hostname, acronimo=acronimo, motivo=msg),
                automatico=automatico,
            )
            conn.commit()
        return payload

    novo_log = substituir_bloco_coleta_fgt(ctx.get("logs_atendimentos") or "", result.logs_text)
    novo_log = sanitize_logs_atendimento_for_db(
        truncate_mysql_text_field(novo_log, max_bytes=LOGS_ATENDIMENTOS_MAX)
    )
    cursor.execute(
        "UPDATE atendimentos SET logs_atendimentos = %s WHERE id_atendimentos = %s",
        (novo_log, id_atendimento),
    )
    ok = result.ok or bool(result.logs_text)
    resumo_admin = extrair_resumo_limpeza_admin_coleta(result.logs_text or "")
    if registrar_auditoria:
        if ok:
            hist = _historico_coleta_sucesso(
                hostname=hostname,
                acronimo=acronimo,
                elapsed_seconds=elapsed,
                commands_run=result.commands_run,
                log_chars=len(novo_log),
                parcial=not result.ok,
                resumo_limpeza_admin=resumo_admin,
                avisos=result.errors or None,
            )
        else:
            motivo = "; ".join(result.errors) or "Coleta sem logs."
            hist = _historico_coleta_falha(
                hostname=hostname,
                acronimo=acronimo,
                motivo=motivo,
                resumo_limpeza_admin=resumo_admin,
            )
        _registrar_historico_caderno(
            conn,
            id_atendimento,
            _CAMPO_HISTORICO_COLETA,
            hist,
            automatico=automatico,
        )
    conn.commit()

    return {
        "ok": ok,
        "message": "Coleta concluída." if result.ok else "Coleta parcial — verifique erros.",
        "commands_run": result.commands_run,
        "errors": result.errors,
        "log_chars": len(novo_log),
        "elapsed_seconds": elapsed,
        "logs_atendimento": novo_log,
    }


def executar_geracao(
    cursor,
    conn,
    id_atendimento: int,
    *,
    questionario: dict,
    imagem_esaq_b64: str,
    portal_banda_larga_ok: bool = True,
    imagem_erro_bbl_b64: str = "",
    imagem_speedtest_b64: str = "",
    executor_vivo: str = "",
    registrar_auditoria: bool = True,
    automatico: bool = False,
    conn_factory=None,
    release_db_before_generate: bool = False,
) -> dict[str, Any]:
    """
    Gera o caderno a partir do atendimento.

    Se ``release_db_before_generate`` e ``conn_factory`` forem usados (API de produção):
    fecha cursor/conn após carregar o contexto, gera o Excel sem segurar MySQL,
    e reabre conexão só para o histórico. Falha no histórico após arquivo gerado
    é logada e não derruba o sucesso da geração.
    """
    from core.logger import get_logger

    log = get_logger("PRODESP")
    ctx = carregar_contexto_atendimento(cursor, id_atendimento)
    if not ctx:
        return {"ok": False, "message": "Atendimento não encontrado."}

    unidade = ctx.get("unidade") or {}
    hostname = (unidade.get("hostname_unidades") or "").strip()
    acronimo = (unidade.get("acronimo_unidades") or "").strip()

    def _audit_with_conn(write_fn) -> None:
        """Executa escrita de histórico; reabre conexão se a prep já foi liberada."""
        if not registrar_auditoria:
            return
        own = False
        c = conn
        if c is None:
            if conn_factory is None:
                log.error(
                    "histórico caderno atendimento=%s: sem conexão disponível",
                    id_atendimento,
                )
                return
            c = conn_factory()
            own = True
        try:
            write_fn(c)
            c.commit()
        except Exception:
            log.exception(
                "histórico caderno atendimento=%s falhou (geração pode ter concluído)",
                id_atendimento,
            )
            try:
                c.rollback()
            except Exception:
                pass
        finally:
            if own:
                try:
                    c.close()
                except Exception:
                    pass

    def _falha(msg: str) -> dict[str, Any]:
        _audit_with_conn(
            lambda c: _registrar_historico_caderno(
                c,
                id_atendimento,
                _CAMPO_HISTORICO_GERACAO,
                _historico_geracao_falha(hostname=hostname, acronimo=acronimo, motivo=msg),
                automatico=automatico,
            )
        )
        return {"ok": False, "message": msg}

    logs = (ctx.get("logs_atendimentos") or "").strip()
    logs_fgt = extrair_bloco_coleta_fgt(logs)
    if not logs_fgt:
        return _falha("Execute a coleta de logs FGT antes de gerar o caderno.")

    voip_tipo = (questionario.get("voip_tipo") or "").strip().upper()
    if voip_tipo in ("CPE", "FGT"):
        if not (questionario.get("voip_nome") or "").strip():
            return _falha("VOIP — Nome do colaborador é obrigatório quando VOIP ≠ N/A.")
        if not (questionario.get("voip_telefone") or "").strip():
            return _falha("VOIP — Telefone fixo é obrigatório quando VOIP ≠ N/A.")

    ok_st, msg_st = validar_status_testes(questionario.get("status_testes") or {})
    if not ok_st:
        return _falha(msg_st)

    ok_q, msg_q = validar_questionario_obrigatorio(questionario)
    if not ok_q:
        return _falha(msg_q)

    dados = {
        "unidade": ctx["unidade"],
        "equipamentos": ctx["equipamentos"],
        "links": ctx["links"],
        "questionario": questionario or {},
        "id_vgr": ctx["unidade"].get("id_vgr_unidades"),
    }

    # Solta MySQL antes do Excel COM (produção).
    if release_db_before_generate and conn_factory is not None:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        # Evita reuso acidental da conexão morta no audit legado.
        conn = None  # type: ignore[assignment]

    try:
        paths = gerar_caderno_prodesp(
            dados,
            logs_text=logs_fgt,
            imagem_esaq_b64=imagem_esaq_b64,
            portal_banda_larga_ok=portal_banda_larga_ok,
            imagem_erro_bbl_b64=imagem_erro_bbl_b64,
            imagem_speedtest_b64=imagem_speedtest_b64,
            executor_vivo=executor_vivo,
        )
    except ValueError as exc:
        return _falha(str(exc))
    except CadernoGeracaoError as exc:
        return _falha(str(exc))
    except FileNotFoundError:
        return _falha("Template do caderno indisponível no servidor.")
    except Exception:
        log.exception("gerar caderno atendimento %s", id_atendimento)
        return _falha("Falha ao gerar caderno. Contate o suporte.")

    path = paths.local
    carimbo_text = ""
    carimbo_source = ""
    try:
        from prodesp.prodesp.caderno.carimbo_noc_export import extrair_texto_carimbo_coluna_e

        if path and os.path.isfile(path):
            carimbo_text = extrair_texto_carimbo_coluna_e(path) or ""
            if carimbo_text:
                ext = os.path.splitext(path)[1].lower()
                carimbo_source = "xlsx" if ext == ".xlsx" else "xlsm"
    except Exception:
        carimbo_text = ""
        carimbo_source = ""

    filename = os.path.basename(path)
    _audit_with_conn(
        lambda c: _registrar_historico_caderno(
            c,
            id_atendimento,
            _CAMPO_HISTORICO_GERACAO,
            _historico_geracao_sucesso(
                filename=filename,
                hostname=hostname,
                acronimo=acronimo,
                copia_rede=bool(paths.rede),
            ),
            automatico=automatico,
        )
    )

    payload: dict[str, Any] = {
        "ok": True,
        "message": mensagem_sucesso_geracao_caderno(copia_rede=bool(paths.rede)),
        "filename": filename,
        "db_released": bool(release_db_before_generate and conn_factory is not None),
    }
    if carimbo_text:
        payload["carimbo_text"] = carimbo_text
        payload["carimbo_source"] = carimbo_source or "caderno"
    return payload


def obter_texto_carimbo_para_atendimento(cursor, id_atendimento: int) -> dict[str, Any]:
    ctx = carregar_contexto_atendimento(cursor, id_atendimento)
    if not ctx:
        return {"ok": False, "message": "Atendimento não encontrado."}

    from prodesp.prodesp.caderno.carimbo_noc_export import obter_texto_carimbo_noc

    id_vgr = str(ctx["unidade"].get("id_vgr_unidades") or "")
    acronimo = str(ctx["unidade"].get("acronimo_unidades") or "")
    id_intragov = str(ctx["unidade"].get("id_intragov_unidades") or "")
    texto, fonte = obter_texto_carimbo_noc(
        id_vgr=id_vgr,
        acronimo=acronimo,
        id_intragov=id_intragov,
        logs_text=ctx.get("logs_atendimentos") or "",
        unidade=ctx.get("unidade") or {},
        equipamentos=ctx.get("equipamentos") or [],
        links=ctx.get("links") or [],
    )
    if not texto:
        return {
            "ok": False,
            "message": "Nenhum dado disponível. Execute a coleta de logs ou gere o caderno.",
        }
    return {"ok": True, "text": texto, "source": fonte}
