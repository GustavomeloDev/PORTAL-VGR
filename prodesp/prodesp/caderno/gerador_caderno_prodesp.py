"""
Geração do caderno de teste PRODESP (.xlsm) a partir do template v3.

Motor padrão: openpyxl (como RD/Itaú) — sem Excel instalado, sem lock COM/OneDrive.
Opcional: PRODESP_CADERNO_ENGINE=excel_com para o fluxo legado via win32.
"""
from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Optional

from openpyxl import load_workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from PIL import Image as PILImage

from prodesp.config_paths import iter_pastas_rede_caderno, network_base_ready
from prodesp.prodesp.caderno.caderno_carimbo_links import (
    montar_bloco_carimbo,
    nome_arquivo_caderno,
    resolver_links_carimbo,
)
from prodesp.prodesp.caderno.caderno_interface_resolver import (
    extrair_aliases_show_interface,
    extrair_arp_por_interface,
    extrair_ips_interfaces_logs,
    montar_show_interface_parts_para_carimbo,
    resolver_interfaces_carimbo,
)
from prodesp.prodesp.caderno.caderno_template_map import (
    CADERNO_CELLS,
    CADERNO_ITEM_ROWS,
    CADERNO_ITEM_ROWS_CLIENTE,
    CARIMBO_CMD_ANCHOR_ROWS,
    CARIMBO_LINK_SAI_BL,
    CARIMBO_LINK_SAI_BLI,
    CARIMBO_LINK_SCM_MPLS,
    CARIMBO_SHOW_INTERFACE_ANCHOR_ROW,
    CADERNO_MODELO_SOLUCAO_VALOR,
    carimbo_log_destino,
    carimbo_log_fim_bloco,
    ESAQ_DISCLAIMER_RANGE,
    ESAQ_IMAGE_CELL,
    ESAQ_IMAGE_CELL_SPEEDTEST,
    ESAQ_IMAGE_HEIGHT_CM,
    ESAQ_IMAGE_WIDTH_CM,
    ESAQ_PORTAL_INDISPONIVEL_TEXTO,
    EXECUTOR_CLIENTE,
    EXECUTOR_VIVO_VITA,
    MODEL_TEMPLATE_FILENAME_XLSM,
    MODEL_TEMPLATE_FILENAME_XLSX,
    STATUS_CONCLUIDO,
    STATUS_PENDENTE,
)
from prodesp.prodesp.caderno.fgt_model_interfaces import (
    normalizar_modelo_exibicao,
)
from prodesp.prodesp.caderno.gerador_caderno_excel_com import (
    ExcelComBusyError,
    ExcelComTimeoutError,
    excel_com_disponivel,
    gerar_caderno_via_excel_com,
)
from prodesp.prodesp.db_field_limits import LOGS_ATENDIMENTOS_MAX

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELO_DIR = os.path.join(BASE_DIR, "static", "caderno_teste", "modelo")


def resolve_gerados_dir(base_dir: str | None = None) -> str:
    """
    Pasta local de cadernos gerados (download portal).
    PRODESP_CADERNO_LOCAL_DIR: caminho fora do OneDrive recomendado em produção.
    """
    local = (os.environ.get("PRODESP_CADERNO_LOCAL_DIR") or "").strip()
    if local:
        return os.path.abspath(local)
    root = base_dir or BASE_DIR
    return os.path.join(root, "static", "caderno_teste", "gerados")


GERADOS_DIR = resolve_gerados_dir()

_MAX_LOG_CHARS = LOGS_ATENDIMENTOS_MAX


class CadernoGeracaoError(RuntimeError):
    """Erro esperado na geração (Excel indisponível, COM falhou, etc.)."""


@dataclass
class CadernoGeradoPaths:
    """Caminho local (download portal) e opcional cópia na rede/OneDrive."""

    local: str
    rede: str | None = None


def _copiar_caderno_para_rede(
    out_path: str,
    acronimo: str,
    *,
    pasta_rede_base: str = "",
) -> str | None:
    dest_dirs = list(
        iter_pastas_rede_caderno(acronimo, base_override=pasta_rede_base)
    )
    log = logging.getLogger("PRODESP")
    for dest_dir in dest_dirs:
        if not dest_dir:
            continue
        if not pasta_rede_base and not network_base_ready(dest_dir):
            log.info("Base de caderno indisponível, tentando fallback: %s", dest_dir)
            continue
        dest_file = os.path.join(dest_dir, os.path.basename(out_path))
        try:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copy2(out_path, dest_file)
            return dest_file
        except OSError as exc:
            log.warning("Caderno não copiado para %s: %s", dest_dir, exc)
    return None


def _resolver_motor_caderno() -> str:
    """
    auto (padrão): Excel COM no Windows (preserva fórmulas/imagens); openpyxl caso contrário.
    openpyxl: apenas dev/Linux — reescreve o template e pode remover imagens e fórmulas.
    """
    raw = (os.environ.get("PRODESP_CADERNO_ENGINE") or "auto").strip().lower()
    if raw in ("excel", "excel_com", "com"):
        return "excel_com"
    if raw == "openpyxl":
        return "openpyxl"
    if sys.platform == "win32" and excel_com_disponivel():
        return "excel_com"
    return "openpyxl"


def _extensao_caderno(modelo_path: str) -> str:
    ext = os.path.splitext(modelo_path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return ext
    return ".xlsx"


def _modelo_path(motor: str) -> str:
    """Preferência: template .xlsx (sem macro); fallback .xlsm."""
    candidatos = (
        os.path.join(MODELO_DIR, MODEL_TEMPLATE_FILENAME_XLSX),
        os.path.join(MODELO_DIR, MODEL_TEMPLATE_FILENAME_XLSM),
    )
    for path in candidatos:
        if os.path.isfile(path):
            if motor == "openpyxl" and path.endswith(".xlsm"):
                logging.getLogger("PRODESP").warning(
                    "openpyxl com template .xlsm: fórmulas/imagens do modelo podem ser perdidas na gravação."
                )
            return path
    raise FileNotFoundError(
        f"Template não encontrado: {os.path.join(MODELO_DIR, MODEL_TEMPLATE_FILENAME_XLSX)}"
    )


def _sanitize_filename(name: str, max_len: int = 120) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    s = re.sub(r"_+", "_", s).strip("._ ")
    return s[:max_len] if len(s) > max_len else s


def _parse_logs_por_comando(logs_text: str) -> dict[str, str]:
    """Última ocorrência de cada comando (evita duplicidade em re-coletas / HA)."""
    from prodesp.prodesp.caderno.fgt_ssh_collector import remover_bloco_fmg_portal

    out: dict[str, str] = {}
    logs_text = remover_bloco_fmg_portal(logs_text or "")
    if not logs_text.strip():
        return out
    parts = re.split(r"---\s*(.+?)\s*---", logs_text, flags=re.DOTALL)
    i = 1
    while i + 1 < len(parts):
        cmd = parts[i].strip()
        body = parts[i + 1].strip()
        if cmd and not cmd.startswith("==="):
            out[cmd] = body
        i += 2
    return out


def _tem_log_show_interface(por_cmd: dict[str, str], ifaces: tuple[str, ...]) -> bool:
    if (por_cmd.get("show sys interface") or "").strip():
        return True
    for iface in ifaces:
        if por_cmd.get(f"show sys interface {iface}"):
            return True
    return False


def _truncate_log(text: str) -> str:
    if not text:
        return ""
    if len(text) <= _MAX_LOG_CHARS:
        return text
    return text[: _MAX_LOG_CHARS - 20] + "\n... (truncado)"


def _build_description(circuito: str, tecnologia: str, id_vantive: str, velocidade: str) -> str:
    from prodesp.prodesp.caderno.caderno_carimbo_links import build_description

    return build_description(circuito, tecnologia, id_vantive, velocidade)


def _decode_imagem_temp(image_b64: str) -> str:
    raw = image_b64.strip()
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]
    data = base64.b64decode(raw)
    pil = PILImage.open(BytesIO(data))
    if pil.mode not in ("RGB", "RGBA"):
        pil = pil.convert("RGB")
    fd, path = tempfile.mkstemp(suffix=".png", prefix="prodesp_esaq_")
    os.close(fd)
    pil.save(path, format="PNG")
    return path


def _normalizar_status_testes(raw: Any) -> dict[int, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[int, str] = {}
    for key, val in raw.items():
        if val is None or str(val).strip() == "":
            continue
        try:
            out[int(key)] = str(val).strip()
        except (TypeError, ValueError):
            continue
    return out


def _montar_itens_status(
    por_cmd: dict[str, str],
    *,
    executor_vivo: str,
    executor_cliente: str,
    tem_esaq: bool,
    status_testes: dict[int, str] | None = None,
    ifaces_coleta: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    status_map = status_testes or {}
    itens: list[dict[str, Any]] = []
    exec_vivo = (executor_vivo or "").strip() or EXECUTOR_VIVO_VITA

    for cmd_key, row in CADERNO_ITEM_ROWS.items():
        if cmd_key == "show sys interface":
            ok = _tem_log_show_interface(por_cmd, ifaces_coleta)
        elif cmd_key == "Site ESAQ":
            ok = tem_esaq
        else:
            ok = bool(por_cmd.get(cmd_key))
        if not ok:
            continue
        if row == 40:
            status = status_map.get(40) or (STATUS_CONCLUIDO if tem_esaq else STATUS_PENDENTE)
        else:
            status = STATUS_CONCLUIDO if ok else STATUS_PENDENTE
        itens.append({"row": row, "executor": exec_vivo, "status": status})

    exec_cli = (executor_cliente or "").strip() or EXECUTOR_CLIENTE
    for row in CADERNO_ITEM_ROWS_CLIENTE:
        itens.append(
            {
                "row": row,
                "executor": exec_cli,
                "status": status_map.get(row, STATUS_PENDENTE),
            }
        )
    return itens


def _top_left_celula(ws, row: int, col: int):
    """Retorna célula gravável (topo-esquerda do merge) — evita MergedCell read-only."""
    from openpyxl.cell.cell import MergedCell

    for merged in ws.merged_cells.ranges:
        if merged.min_row <= row <= merged.max_row and merged.min_col <= col <= merged.max_col:
            return ws.cell(merged.min_row, merged.min_col)
    cell = ws.cell(row, col)
    if isinstance(cell, MergedCell):
        for merged in ws.merged_cells.ranges:
            if merged.min_row <= row <= merged.max_row and merged.min_col <= col <= merged.max_col:
                return ws.cell(merged.min_row, merged.min_col)
    return cell


def _openpyxl_add_image_from_b64(ws, image_b64: str, anchor_cell: str) -> None:
    raw = image_b64.strip()
    if raw.startswith("data:"):
        raw = raw.split(",", 1)[-1]
    data = base64.b64decode(raw)
    pil = PILImage.open(BytesIO(data))
    if pil.mode not in ("RGB", "RGBA"):
        pil = pil.convert("RGB")
    buf = BytesIO()
    pil.save(buf, format="PNG")
    buf.seek(0)
    img = OpenpyxlImage(buf)
    dpi = 96
    img.height = int(ESAQ_IMAGE_HEIGHT_CM * dpi / 2.54)
    img.width = int(ESAQ_IMAGE_WIDTH_CM * dpi / 2.54)
    ws.add_image(img, anchor_cell)


def _gerar_openpyxl(
    modelo_src: str,
    out_path: str,
    *,
    valores: dict[str, Any],
    link_sai_bl: dict[str, Any],
    link_scm: dict[str, Any],
    link_sai_bli: Optional[dict[str, Any]] = None,
    por_cmd: dict[str, str],
    show_parts: list[str],
    itens: list[dict[str, Any]],
    imagem_esaq_b64: str,
    portal_banda_larga_ok: bool = True,
    imagem_erro_bbl_b64: str = "",
    imagem_speedtest_b64: str = "",
) -> None:
    shutil.copy2(modelo_src, out_path)
    wb = load_workbook(out_path, keep_vba=False)
    ws = wb["CADERNO DE TESTE"]
    ws_car = wb["CARIMBO NOC"]
    ws_esaq = wb["TESTE_DE_BANDA_ESAQ"]

    for key, cell in CADERNO_CELLS.items():
        if valores.get(key) is not None and valores.get(key) != "":
            ws[cell] = valores[key]

    for field, row in CARIMBO_LINK_SAI_BL.items():
        if link_sai_bl.get(field) is not None:
            ws_car.cell(row, 4).value = link_sai_bl[field]
    if link_sai_bli:
        for field, row in CARIMBO_LINK_SAI_BLI.items():
            if link_sai_bli.get(field) is not None:
                ws_car.cell(row, 4).value = link_sai_bli[field]
    else:
        for row in CARIMBO_LINK_SAI_BLI.values():
            ws_car.cell(row, 4).value = ""
    for field, row in CARIMBO_LINK_SCM_MPLS.items():
        if link_scm.get(field) is not None:
            ws_car.cell(row, 4).value = link_scm[field]

    def paste_log(cmd_anchor_row: int, text: str) -> None:
        body = _truncate_log(text)
        if not body:
            return
        start_row, col = carimbo_log_destino(cmd_anchor_row)
        end_row = carimbo_log_fim_bloco(cmd_anchor_row)
        lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        max_lines = max(1, end_row - start_row + 1)
        if len(lines) > max_lines:
            lines = lines[: max_lines - 1] + ["... (truncado)"]
        for offset in range(max_lines):
            row = start_row + offset
            cell = _top_left_celula(ws_car, row, col)
            cell.value = lines[offset] if offset < len(lines) else None
            try:
                from openpyxl.styles import Alignment

                cell.alignment = Alignment(wrap_text=True, vertical="top")
            except Exception:
                pass

    for cmd, body in por_cmd.items():
        if cmd.startswith("show sys interface "):
            continue
        anchor = CARIMBO_CMD_ANCHOR_ROWS.get(cmd)
        if anchor:
            paste_log(anchor, body)
    if show_parts:
        paste_log(CARIMBO_SHOW_INTERFACE_ANCHOR_ROW, "\n\n".join(show_parts))

    for item in itens:
        row = item["row"]
        if item.get("executor"):
            ws.cell(row, 4).value = item["executor"]
        if item.get("status"):
            ws.cell(row, 5).value = item["status"]

    if portal_banda_larga_ok:
        _openpyxl_add_image_from_b64(ws_esaq, imagem_esaq_b64, ESAQ_IMAGE_CELL)
    else:
        _openpyxl_add_image_from_b64(ws_esaq, imagem_erro_bbl_b64, ESAQ_IMAGE_CELL)
        _openpyxl_add_image_from_b64(ws_esaq, imagem_speedtest_b64, ESAQ_IMAGE_CELL_SPEEDTEST)
        ws_esaq.merge_cells(ESAQ_DISCLAIMER_RANGE)
        ws_esaq[ESAQ_DISCLAIMER_RANGE.split(":")[0]] = ESAQ_PORTAL_INDISPONIVEL_TEXTO
        try:
            from openpyxl.styles import Alignment

            ws_esaq[ESAQ_DISCLAIMER_RANGE.split(":")[0]].alignment = Alignment(
                wrap_text=True, vertical="top"
            )
        except Exception:
            pass

    wb.save(out_path)


def _salvar_caderno_openpyxl(modelo_src: str, out_path: str, **kwargs: Any) -> None:
    """Grava via openpyxl em arquivo temporário na pasta destino e substitui (evita lock)."""
    dest_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(dest_dir, exist_ok=True)
    suffix = os.path.splitext(out_path)[1] or ".xlsx"

    last_exc: OSError | None = None
    for attempt in range(6):
        fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix="caderno_", dir=dest_dir)
        os.close(fd)
        try:
            os.remove(temp_path)
        except OSError:
            pass
        try:
            _gerar_openpyxl(modelo_src, temp_path, **kwargs)
            if os.path.isfile(out_path):
                try:
                    os.remove(out_path)
                except OSError:
                    pass
            os.replace(temp_path, out_path)
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(0.35 * (attempt + 1))
        finally:
            if os.path.isfile(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    nome = os.path.basename(out_path)
    raise OSError(
        f"Não foi possível gravar o caderno '{nome}' "
        f"(arquivo em uso ou bloqueio do OneDrive)."
    ) from last_exc


def gerar_caderno_prodesp(
    dados: dict[str, Any],
    *,
    logs_text: str = "",
    imagem_esaq_b64: str = "",
    portal_banda_larga_ok: bool = True,
    imagem_erro_bbl_b64: str = "",
    imagem_speedtest_b64: str = "",
    pasta_rede: str = "",
    executor_vivo: str = "",
) -> CadernoGeradoPaths:
    portal_ok = bool(portal_banda_larga_ok)
    if portal_ok:
        if not imagem_esaq_b64:
            raise ValueError("Imagem ESAQ obrigatória para gerar o caderno.")
    else:
        if not imagem_erro_bbl_b64 or not imagem_speedtest_b64:
            raise ValueError(
                "Com Portal Banda Larga indisponível, informe a evidência de erro e a do Speedtest."
            )

    motor = _resolver_motor_caderno()
    modelo_src = _modelo_path(motor)
    ext = _extensao_caderno(modelo_src)

    gerados_dir = resolve_gerados_dir()
    os.makedirs(gerados_dir, exist_ok=True)

    unidade = dados.get("unidade") or {}
    equipamentos = dados.get("equipamentos") or []
    links = dados.get("links") or []
    q = dados.get("questionario") or {}

    eq_prim = equipamentos[0] if equipamentos else {}
    modelo_raw = eq_prim.get("modelo_equipamentos") or eq_prim.get("modelo") or ""
    modelo = normalizar_modelo_exibicao(modelo_raw)
    serials = [
        (e.get("serial_equipamentos") or e.get("serial") or "").strip()
        for e in equipamentos
        if (e.get("serial_equipamentos") or e.get("serial") or "").strip()
    ]
    serial_txt = serials[0] if len(serials) == 1 else " / ".join(serials) if serials else ""
    ha = "SIM" if len(serials) > 1 else "NÃO"

    links_res = resolver_links_carimbo(links)
    id_vgr = str(unidade.get("id_vgr_unidades") or dados.get("id_vgr") or "").strip()

    acronimo = unidade.get("acronimo_unidades") or unidade.get("acronimo") or ""

    fname = _sanitize_filename(nome_arquivo_caderno(unidade))
    out_path = os.path.join(gerados_dir, f"{fname}{ext}")

    valores = {
        "id_intragov": (
            (unidade.get("id_intragov_unidades") or unidade.get("id_intragov") or "")
            .replace("/", "-")
        ),
        "id_vgr": id_vgr,
        "acronimo": unidade.get("acronimo_unidades") or unidade.get("acronimo") or "",
        "site_name": unidade.get("site_name_unidades") or unidade.get("site_name") or "",
        "localidade": unidade.get("localidade_unidades") or unidade.get("localidade") or "",
        "topologia": unidade.get("topologia_unidades") or unidade.get("topologia") or "SD-WAN",
        "modelo_solucao": unidade.get("modelo_solucao_unidades") or CADERNO_MODELO_SOLUCAO_VALOR,
        "fornecedor": "Fortinet",
        "modelo_equipamento": modelo,
        "redundancia_ha": ha,
        "hostname_primario": (unidade.get("hostname_unidades") or unidade.get("hostname") or "").lower(),
        "serial_primario": serial_txt,
        "ip_mgmt": unidade.get("loopback_vivo_unidades") or unidade.get("loopback_vivo") or "",
        "dhcp_server": q.get("dhcp_server", ""),
        "dhcp_relay": q.get("dhcp_relay", ""),
        "vlan": q.get("vlan", ""),
        "multi_ip_lan": q.get("multi_ip_lan", ""),
        "voip_tipo": q.get("voip_tipo", ""),
        "voip_nome": q.get("voip_nome", ""),
        "voip_telefone": q.get("voip_telefone", ""),
    }

    por_cmd = _parse_logs_por_comando(logs_text)
    aliases_iface = extrair_aliases_show_interface(por_cmd)
    iface_ips = extrair_ips_interfaces_logs(por_cmd)
    arp_por_iface = extrair_arp_por_interface(por_cmd)
    ifaces_por_link = resolver_interfaces_carimbo(aliases_iface, links_res, modelo, por_cmd)

    def _ip_log_iface(nome_iface: str) -> str:
        if not nome_iface:
            return ""
        return iface_ips.get(nome_iface.lower(), "") or ""

    def _arp_iface(nome_iface: str) -> list[str]:
        if not nome_iface:
            return []
        return arp_por_iface.get(nome_iface.lower(), []) or []

    link_sai_bl = montar_bloco_carimbo(
        links_res.sai_bl,
        interface=ifaces_por_link.get("sai_bl", ""),
        circuito="SAI-BL",
        tecnologia="INET1",
        ip_interface_log=_ip_log_iface(ifaces_por_link.get("sai_bl", "")),
        arp_neighbors=_arp_iface(ifaces_por_link.get("sai_bl", "")),
    )
    link_scm = montar_bloco_carimbo(
        links_res.scm,
        interface=ifaces_por_link.get("scm", ""),
        circuito="SCM",
        tecnologia="MPLS1",
        ip_interface_log=_ip_log_iface(ifaces_por_link.get("scm", "")),
        arp_neighbors=_arp_iface(ifaces_por_link.get("scm", "")),
    )
    link_sai_bli_dict: Optional[dict[str, str]] = None
    if links_res.incluir_sai_bli and ifaces_por_link.get("sai_bli"):
        candidato = montar_bloco_carimbo(
            links_res.sai_bli,
            interface=ifaces_por_link["sai_bli"],
            circuito="SAI-BLI",
            tecnologia="INET2",
            ip_interface_log=_ip_log_iface(ifaces_por_link["sai_bli"]),
            arp_neighbors=_arp_iface(ifaces_por_link["sai_bli"]),
        )
        from prodesp.prodesp.caderno.caderno_carimbo_links import deve_exibir_bloco_sai_bli_no_carimbo

        if deve_exibir_bloco_sai_bli_no_carimbo(candidato):
            link_sai_bli_dict = candidato

    ifaces_resolvidas = tuple(
        x
        for x in (
            link_sai_bl.get("interface"),
            link_scm.get("interface"),
            (link_sai_bli_dict or {}).get("interface"),
        )
        if x
    )
    show_parts = montar_show_interface_parts_para_carimbo(por_cmd, ifaces_resolvidas)

    itens = _montar_itens_status(
        por_cmd,
        executor_vivo=executor_vivo or q.get("executor_vivo", ""),
        executor_cliente=q.get("executor_cliente", ""),
        tem_esaq=bool(imagem_esaq_b64 or imagem_erro_bbl_b64 or imagem_speedtest_b64),
        status_testes=_normalizar_status_testes(q.get("status_testes")),
        ifaces_coleta=ifaces_resolvidas,
    )

    kwargs_openpyxl: dict[str, Any] = {
        "valores": valores,
        "link_sai_bl": link_sai_bl,
        "link_scm": link_scm,
        "link_sai_bli": link_sai_bli_dict,
        "por_cmd": por_cmd,
        "show_parts": show_parts,
        "itens": itens,
        "portal_banda_larga_ok": portal_ok,
        "imagem_esaq_b64": imagem_esaq_b64 if portal_ok else "",
        "imagem_erro_bbl_b64": imagem_erro_bbl_b64 if not portal_ok else "",
        "imagem_speedtest_b64": imagem_speedtest_b64 if not portal_ok else "",
    }

    logging.getLogger("PRODESP").info(
        "Gerando caderno %s via motor %s (template %s) em %s",
        fname,
        motor,
        os.path.basename(modelo_src),
        out_path,
    )
    temp_paths: list[str] = []
    try:
        if motor == "openpyxl":
            logging.getLogger("PRODESP").warning(
                "Motor openpyxl: imagens e fórmulas complexas do template podem ser removidas pelo Excel. "
                "Em produção Windows use PRODESP_CADERNO_ENGINE=auto (Excel COM)."
            )
            try:
                _salvar_caderno_openpyxl(modelo_src, out_path, **kwargs_openpyxl)
            except OSError as exc:
                raise CadernoGeracaoError(str(exc)) from exc
        else:
            if not excel_com_disponivel():
                raise CadernoGeracaoError(
                    "Geração via Excel COM requer Microsoft Excel instalado no servidor Windows."
                )
            kwargs_com: dict[str, Any] = {
                "portal_banda_larga_ok": portal_ok,
            }
            if portal_ok:
                img_temp = _decode_imagem_temp(imagem_esaq_b64)
                temp_paths.append(img_temp)
                kwargs_com["image_temp_path"] = img_temp
            else:
                img_erro = _decode_imagem_temp(imagem_erro_bbl_b64)
                img_speed = _decode_imagem_temp(imagem_speedtest_b64)
                temp_paths.extend([img_erro, img_speed])
                kwargs_com["image_erro_bbl_path"] = img_erro
                kwargs_com["image_speedtest_path"] = img_speed
            try:
                gerar_caderno_via_excel_com(
                    modelo_src,
                    out_path,
                    valores_caderno=valores,
                    link_sai_bl=link_sai_bl,
                    link_scm=link_scm,
                    link_sai_bli=link_sai_bli_dict,
                    logs_por_cmd=por_cmd,
                    show_interface_parts=show_parts,
                    itens_executor_status=itens,
                    **kwargs_com,
                )
            except ExcelComBusyError as exc:
                raise CadernoGeracaoError(str(exc)) from exc
            except ExcelComTimeoutError as exc:
                raise CadernoGeracaoError(str(exc)) from exc
            except CadernoGeracaoError:
                raise
            except OSError as exc:
                raise CadernoGeracaoError(str(exc)) from exc
            except Exception as exc:
                raise CadernoGeracaoError(
                    "Falha ao gerar o caderno via Microsoft Excel. "
                    "Verifique se o Excel está instalado e disponível."
                ) from exc
    finally:
        for p in temp_paths:
            try:
                os.remove(p)
            except OSError:
                pass

    rede_path = _copiar_caderno_para_rede(
        out_path,
        acronimo,
        pasta_rede_base=(pasta_rede or "").strip(),
    )
    return CadernoGeradoPaths(local=out_path, rede=rede_path)
