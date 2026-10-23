"""
Geração do caderno via Excel COM (win32) — preserva fórmulas, validações, links externos e imagens.
Suporta template/saída .xlsx (sem macro) ou .xlsm.

Excel COM tolera poucas instâncias no mesmo host: gerações são limitadas por pool de processo
(PRODESP_CADERNO_EXCEL_POOL_SIZE, padrão 2; PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC).

Cada job tem teto duro (PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC, padrão 170s): se o Excel travar,
o Portal mata o PID daquela instância e libera o slot — evita workers eternamente bloqueados.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from prodesp.prodesp.db_field_limits import LOGS_ATENDIMENTOS_MAX
from prodesp.prodesp.caderno.caderno_template_map import (
    CADERNO_CELLS,
    CARIMBO_CMD_ANCHOR_ROWS,
    CARIMBO_LINK_SAI_BL,
    CARIMBO_LINK_SAI_BLI,
    CARIMBO_LINK_SCM_MPLS,
    CARIMBO_LOG_MERGE_RANGES,
    CARIMBO_SHOW_INTERFACE_ANCHOR_ROW,
    ESAQ_DISCLAIMER_RANGE,
    ESAQ_IMAGE_CELL,
    ESAQ_IMAGE_CELL_SPEEDTEST,
    ESAQ_IMAGE_HEIGHT_CM,
    ESAQ_IMAGE_WIDTH_CM,
    ESAQ_PORTAL_INDISPONIVEL_TEXTO,
    carimbo_log_destino,
    carimbo_log_fim_bloco,
)

logger = logging.getLogger(__name__)

_CM_TO_PT = 28.3464566929

# Pool de slots DispatchEx/Excel no processo do Portal (Waitress multi-thread).
_POOL_INIT_LOCK = threading.Lock()
_EXCEL_COM_POOL: threading.BoundedSemaphore | None = None
_EXCEL_COM_POOL_SIZE = 0
_EXCEL_COM_ACTIVE = 0
_EXCEL_COM_ACTIVE_LOCK = threading.Lock()

_DEFAULT_POOL_SIZE = 2
_MAX_POOL_SIZE = 4
# Alinhado ao AbortController da UI (180s): servidor corta um pouco antes.
_DEFAULT_JOB_TIMEOUT_SEC = 170.0
_MIN_JOB_TIMEOUT_SEC = 1.0
_MAX_JOB_TIMEOUT_SEC = 300.0


def _msg_excel_com_ocupado(pool_size: int) -> str:
    return (
        f"O limite de gerações simultâneas de caderno via Excel no servidor foi atingido "
        f"(máximo {pool_size}). Aguarde cerca de 1 minuto e tente novamente."
    )


def _msg_excel_com_timeout(timeout_sec: float) -> str:
    return (
        f"A geração do caderno via Excel excedeu o tempo limite "
        f"({int(timeout_sec)}s) e foi interrompida. Tente novamente; "
        f"se repetir, verifique Excel/OneDrive no servidor do Portal."
    )


class ExcelComBusyError(RuntimeError):
    """Pool de Excel COM esgotado (todas as slots em uso além do tempo de espera)."""


class ExcelComTimeoutError(RuntimeError):
    """Geração Excel COM excedeu PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC (instância morta)."""


def excel_com_disponivel() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


def _excel_com_lock_wait_sec() -> float:
    """Tempo máximo aguardando slot livre (env PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC)."""
    raw = (os.environ.get("PRODESP_CADERNO_EXCEL_LOCK_WAIT_SEC") or "60").strip()
    try:
        return max(5.0, min(float(raw), 300.0))
    except ValueError:
        return 60.0


def _excel_com_pool_size() -> int:
    """Slots paralelos de Excel COM (env PRODESP_CADERNO_EXCEL_POOL_SIZE, padrão 2, máx. 4)."""
    raw = (os.environ.get("PRODESP_CADERNO_EXCEL_POOL_SIZE") or str(_DEFAULT_POOL_SIZE)).strip()
    try:
        return max(1, min(int(raw), _MAX_POOL_SIZE))
    except ValueError:
        return _DEFAULT_POOL_SIZE


def _excel_com_job_timeout_sec() -> float:
    """
    Teto duro de uma geração COM (env PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC).
    Padrão 170s — sob o timeout da UI (180s) para devolver JSON amigável quando possível.
    """
    raw = (os.environ.get("PRODESP_CADERNO_EXCEL_JOB_TIMEOUT_SEC") or "").strip()
    if not raw:
        return _DEFAULT_JOB_TIMEOUT_SEC
    try:
        return max(_MIN_JOB_TIMEOUT_SEC, min(float(raw), _MAX_JOB_TIMEOUT_SEC))
    except ValueError:
        return _DEFAULT_JOB_TIMEOUT_SEC


def _excel_application_pid(excel: Any) -> int | None:
    """PID do processo Excel.Application (win32); None se indisponível."""
    try:
        import win32process

        hwnd = int(excel.Hwnd)
        _tid, pid = win32process.GetWindowThreadProcessId(hwnd)
        pid_i = int(pid or 0)
        return pid_i if pid_i > 0 else None
    except Exception as exc:
        logger.warning("excel_com: não foi possível obter PID do Excel: %s", exc)
        return None


def _kill_excel_pid(pid: int) -> None:
    """Força encerramento do Excel (e árvore) após timeout — só o PID da geração."""
    if not pid or pid <= 0:
        return
    logger.warning("excel_com: timeout — matando Excel PID %s (/F /T)", pid)
    try:
        completed = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if completed.returncode not in (0, 128, 255):
            logger.warning(
                "excel_com: taskkill PID %s rc=%s out=%s err=%s",
                pid,
                completed.returncode,
                (completed.stdout or "").strip()[:200],
                (completed.stderr or "").strip()[:200],
            )
    except Exception:
        logger.exception("excel_com: falha ao matar Excel PID %s", pid)


def _ensure_excel_com_pool() -> tuple[threading.BoundedSemaphore, int]:
    """Inicializa o semáforo na 1ª uso (tamanho fixo até reset de teste/reinício)."""
    global _EXCEL_COM_POOL, _EXCEL_COM_POOL_SIZE
    with _POOL_INIT_LOCK:
        if _EXCEL_COM_POOL is None:
            size = _excel_com_pool_size()
            _EXCEL_COM_POOL_SIZE = size
            _EXCEL_COM_POOL = threading.BoundedSemaphore(size)
            logger.info("excel_com: pool inicializado com %s slot(s)", size)
        return _EXCEL_COM_POOL, _EXCEL_COM_POOL_SIZE


def reset_excel_com_pool_for_tests() -> None:
    """Recria o pool (apenas testes). Falha se houver slot em uso."""
    global _EXCEL_COM_POOL, _EXCEL_COM_POOL_SIZE, _EXCEL_COM_ACTIVE
    with _POOL_INIT_LOCK:
        with _EXCEL_COM_ACTIVE_LOCK:
            if _EXCEL_COM_ACTIVE:
                raise RuntimeError(
                    f"reset_excel_com_pool_for_tests com {_EXCEL_COM_ACTIVE} slot(s) ativo(s)"
                )
            _EXCEL_COM_ACTIVE = 0
        _EXCEL_COM_POOL = None
        _EXCEL_COM_POOL_SIZE = 0


@contextmanager
def excel_com_serializado() -> Iterator[None]:
    """Reserva um slot do pool Excel COM (até N gerações paralelas neste processo)."""
    global _EXCEL_COM_ACTIVE
    pool, pool_size = _ensure_excel_com_pool()
    wait = _excel_com_lock_wait_sec()
    logger.info(
        "excel_com: aguardando slot do pool (tamanho=%s, até %.0fs)",
        pool_size,
        wait,
    )
    acquired = pool.acquire(timeout=wait)
    if not acquired:
        logger.warning(
            "excel_com: pool esgotado (tamanho=%s) após %.0fs de espera",
            pool_size,
            wait,
        )
        raise ExcelComBusyError(_msg_excel_com_ocupado(pool_size))
    with _EXCEL_COM_ACTIVE_LOCK:
        _EXCEL_COM_ACTIVE += 1
        active = _EXCEL_COM_ACTIVE
    started = time.monotonic()
    try:
        logger.info("excel_com: slot adquirido (ativos %s/%s)", active, pool_size)
        yield
    finally:
        with _EXCEL_COM_ACTIVE_LOCK:
            _EXCEL_COM_ACTIVE = max(0, _EXCEL_COM_ACTIVE - 1)
            active_after = _EXCEL_COM_ACTIVE
        pool.release()
        logger.info(
            "excel_com: slot liberado (durou %.1fs; ativos %s/%s)",
            time.monotonic() - started,
            active_after,
            pool_size,
        )


def _criar_arquivo_temporario(
    prefix: str,
    *,
    suffix: str = ".xlsx",
    dir: str | None = None,
) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
    os.close(fd)
    try:
        os.remove(path)
    except OSError:
        pass
    return path


def _excel_file_format(path: str) -> int:
    """51 = xlsx, 52 = xlsm (Excel constants)."""
    if (path or "").lower().endswith(".xlsm"):
        return 52
    return 51


def _aguardar_arquivo_livre(path: str, *, timeout: float = 20.0, interval: float = 0.35) -> None:
    """Aguarda Excel/OneDrive liberarem o arquivo após SaveAs/Close."""
    path_abs = os.path.abspath(path)
    if not os.path.isfile(path_abs):
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(path_abs, "r+b"):
                return
        except OSError:
            time.sleep(interval)


def _encerrar_excel_com(excel: Any, wb: Any) -> None:
    """Fecha workbook e Excel COM; aguarda liberação de lock no Windows."""
    import gc

    if wb is not None:
        try:
            wb.Saved = True
            wb.Close(SaveChanges=False)
        except Exception:
            pass
    if excel is not None:
        try:
            excel.DisplayAlerts = False
            excel.Quit()
        except Exception:
            pass
    del wb, excel
    gc.collect()
    time.sleep(1.0)


def _publicar_caderno_gerado(temp_path: str, dest_path: str, *, retries: int = 12) -> None:
    """Publica temp → destino final com retry (OneDrive / arquivo em uso)."""
    temp_abs = os.path.abspath(temp_path)
    dest_abs = os.path.abspath(dest_path)
    if temp_abs == dest_abs:
        return
    os.makedirs(os.path.dirname(dest_abs), exist_ok=True)
    _aguardar_arquivo_livre(temp_abs)

    partial_abs = dest_abs + ".partial"
    last_exc: OSError | None = None

    for attempt in range(retries):
        try:
            shutil.copy2(temp_abs, partial_abs)
            if os.path.isfile(dest_abs):
                try:
                    os.remove(dest_abs)
                except OSError:
                    pass
            os.replace(partial_abs, dest_abs)
            try:
                os.remove(temp_abs)
            except OSError:
                pass
            return
        except OSError as exc:
            last_exc = exc
            try:
                if os.path.isfile(partial_abs):
                    os.remove(partial_abs)
            except OSError:
                pass
            delay = 0.5 * (attempt + 1)
            logger.warning(
                "Publicação caderno tentativa %s/%s falhou (%s); aguardando %.1fs",
                attempt + 1,
                retries,
                exc,
                delay,
            )
            time.sleep(delay)

    for attempt in range(4):
        try:
            if os.path.isfile(dest_abs):
                try:
                    os.remove(dest_abs)
                except OSError:
                    pass
            os.replace(temp_abs, dest_abs)
            return
        except OSError as exc:
            last_exc = exc
            time.sleep(0.75 * (attempt + 1))

    nome = os.path.basename(dest_abs)
    raise OSError(
        f"Não foi possível gravar o caderno '{nome}' na pasta de saída "
        f"(arquivo em uso ou bloqueio do OneDrive). "
        f"Defina PRODESP_CADERNO_LOCAL_DIR fora do OneDrive se o problema persistir."
    ) from last_exc


def _truncate_log(text: str, max_chars: int = LOGS_ATENDIMENTOS_MAX) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n... (truncado)"


def _escrever_texto_celula(cell, text: str) -> None:
    """Grava texto literal via COM — evita interpretação de fórmula quando começa com '='."""
    if not text:
        return
    cell.NumberFormat = "@"
    cell.Value2 = text
    try:
        cell.WrapText = True
        cell.VerticalAlignment = -4160  # xlTop
    except Exception:
        pass


def _normalizar_linhas_log(text: str) -> list[str]:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _paste_log_com(ws_car, cmd_anchor_row: int, text: str) -> None:
    body = _truncate_log(text)
    if not body:
        return
    start_row, col = carimbo_log_destino(cmd_anchor_row)
    end_row = carimbo_log_fim_bloco(cmd_anchor_row)
    lines = _normalizar_linhas_log(body)
    max_lines = max(1, end_row - start_row + 1)
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + ["... (truncado)"]

    try:
        ws_car.Range(
            ws_car.Cells(start_row, col),
            ws_car.Cells(end_row, col),
        ).ClearContents()
    except Exception:
        pass

    for offset, line in enumerate(lines):
        row = start_row + offset
        if row > end_row:
            break
        cell = ws_car.Cells(row, col)
        try:
            if cell.MergeCells:
                merge_addr = cell.MergeArea.Address
                cell.MergeArea.UnMerge()
                target = ws_car.Cells(row, col)
                target.ClearContents()
                _escrever_texto_celula(target, line)
                ws_car.Range(merge_addr).Merge()
                continue
        except Exception:
            pass
        try:
            cell.ClearContents()
        except Exception:
            pass
        _escrever_texto_celula(cell, line)


def _set(ws, addr: str, value: Any) -> None:
    if value is None or value == "":
        return
    ws.Range(addr).Value = value


def _preparar_area_logs_com(ws_car) -> list[str]:
    """Desfaz merges dos blocos de log (col B) para permitir escrita via COM."""
    remerged: list[str] = []
    for addr in CARIMBO_LOG_MERGE_RANGES:
        try:
            rng = ws_car.Range(addr)
            if rng.MergeCells:
                rng.UnMerge()
                remerged.append(addr)
        except Exception:
            pass
    return remerged


def _restaurar_merges_com(ws_car, ranges: list[str]) -> None:
    for addr in ranges:
        try:
            ws_car.Range(addr).Merge()
        except Exception:
            pass


def _inserir_imagem_esaq_com(ws_esaq, image_path: str, anchor_cell: str = ESAQ_IMAGE_CELL) -> None:
    rng = ws_esaq.Range(anchor_cell)
    left = float(rng.Left)
    top = float(rng.Top)
    width = ESAQ_IMAGE_WIDTH_CM * _CM_TO_PT
    height = ESAQ_IMAGE_HEIGHT_CM * _CM_TO_PT
    # Substitui apenas imagens na área ESAQ (preserva demais desenhos da aba)
    anchor = rng.MergeArea if rng.MergeCells else rng
    a_left = float(anchor.Left)
    a_top = float(anchor.Top)
    a_right = a_left + float(anchor.Width)
    a_bottom = a_top + float(anchor.Height)
    for i in range(ws_esaq.Shapes.Count, 0, -1):
        try:
            shp = ws_esaq.Shapes.Item(i)
            if shp.Type != 13:  # msoPicture
                continue
            s_left = float(shp.Left)
            s_top = float(shp.Top)
            if s_left >= a_left - 2 and s_top >= a_top - 2 and s_left < a_right and s_top < a_bottom:
                shp.Delete()
        except Exception:
            pass
    ws_esaq.Shapes.AddPicture(
        os.path.abspath(image_path),
        False,
        True,
        left,
        top,
        width,
        height,
    )


def _inserir_disclaimer_portal_indisponivel_com(
    ws_esaq,
    texto: str = ESAQ_PORTAL_INDISPONIVEL_TEXTO,
    merge_range: str = ESAQ_DISCLAIMER_RANGE,
) -> None:
    rng = ws_esaq.Range(merge_range)
    try:
        if not rng.MergeCells:
            rng.Merge()
    except Exception:
        pass
    rng.Value2 = texto
    try:
        rng.WrapText = True
        rng.VerticalAlignment = -4160  # xlTop
        rng.HorizontalAlignment = -4131  # xlLeft
    except Exception:
        pass


def gerar_caderno_via_excel_com(
    modelo_src: str,
    out_path: str,
    *,
    valores_caderno: dict[str, Any],
    link_sai_bl: dict[str, Any],
    link_scm: dict[str, Any],
    link_sai_bli: Optional[dict[str, Any]] = None,
    logs_por_cmd: dict[str, str],
    show_interface_parts: list[str],
    itens_executor_status: list[dict[str, Any]],
    image_temp_path: Optional[str] = None,
    image_erro_bbl_path: Optional[str] = None,
    image_speedtest_path: Optional[str] = None,
    portal_banda_larga_ok: bool = True,
) -> None:
    """
    Reserva slot do pool e executa a geração COM em thread dedicada com teto duro.
    Em timeout: mata o PID do Excel dessa geração e libera o slot.
    """
    timeout_sec = _excel_com_job_timeout_sec()
    with excel_com_serializado():
        pid_box: dict[str, Any] = {"pid": None}
        error_box: dict[str, BaseException] = {}
        done = threading.Event()

        def _runner() -> None:
            try:
                _gerar_caderno_via_excel_com_locked(
                    modelo_src,
                    out_path,
                    valores_caderno=valores_caderno,
                    link_sai_bl=link_sai_bl,
                    link_scm=link_scm,
                    link_sai_bli=link_sai_bli,
                    logs_por_cmd=logs_por_cmd,
                    show_interface_parts=show_interface_parts,
                    itens_executor_status=itens_executor_status,
                    image_temp_path=image_temp_path,
                    image_erro_bbl_path=image_erro_bbl_path,
                    image_speedtest_path=image_speedtest_path,
                    portal_banda_larga_ok=portal_banda_larga_ok,
                    pid_box=pid_box,
                )
            except BaseException as exc:
                error_box["exc"] = exc
            finally:
                done.set()

        worker = threading.Thread(
            target=_runner,
            name="prodesp-caderno-excel-com",
            daemon=True,
        )
        logger.info("excel_com: iniciando job (timeout=%.0fs)", timeout_sec)
        worker.start()
        finished = done.wait(timeout=timeout_sec)
        if not finished:
            pid = pid_box.get("pid")
            logger.error(
                "excel_com: job excedeu %.0fs — forçando kill (pid=%s)",
                timeout_sec,
                pid,
            )
            if pid:
                _kill_excel_pid(int(pid))
            # Aguarda cleanup do worker após taskkill (COM tende a falhar rápido).
            done.wait(timeout=45.0)
            raise ExcelComTimeoutError(_msg_excel_com_timeout(timeout_sec))
        worker.join(timeout=5.0)
        if "exc" in error_box:
            raise error_box["exc"]


def _gerar_caderno_via_excel_com_locked(
    modelo_src: str,
    out_path: str,
    *,
    valores_caderno: dict[str, Any],
    link_sai_bl: dict[str, Any],
    link_scm: dict[str, Any],
    link_sai_bli: Optional[dict[str, Any]] = None,
    logs_por_cmd: dict[str, str],
    show_interface_parts: list[str],
    itens_executor_status: list[dict[str, Any]],
    image_temp_path: Optional[str] = None,
    image_erro_bbl_path: Optional[str] = None,
    image_speedtest_path: Optional[str] = None,
    portal_banda_larga_ok: bool = True,
    pid_box: Optional[dict[str, Any]] = None,
) -> None:
    import pythoncom
    import win32com.client

    out_abs = os.path.abspath(out_path)
    dest_dir = os.path.dirname(out_abs) or "."
    os.makedirs(dest_dir, exist_ok=True)
    ext = os.path.splitext(out_abs)[1].lower() or os.path.splitext(modelo_src)[1].lower() or ".xlsx"
    if ext not in (".xlsx", ".xlsm"):
        ext = ".xlsx"

    temp_modelo = _criar_arquivo_temporario("prodesp_caderno_tpl_", suffix=ext)
    work_dir = (os.environ.get("PRODESP_CADERNO_WORK_DIR") or "").strip() or None
    # SaveAs fora do OneDrive — Excel segura lock no arquivo; publicação copia para gerados/ depois.
    temp_saida = _criar_arquivo_temporario("prodesp_caderno_out_", suffix=ext, dir=work_dir)
    shutil.copy2(modelo_src, temp_modelo)
    gerado_ok = False

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        if pid_box is not None:
            pid_box["pid"] = _excel_application_pid(excel)
            logger.info("excel_com: DispatchEx pid=%s", pid_box.get("pid"))
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.ScreenUpdating = False

        wb = excel.Workbooks.Open(temp_modelo, UpdateLinks=0, ReadOnly=False)
        ws = wb.Sheets("CADERNO DE TESTE")
        ws_car = wb.Sheets("CARIMBO NOC")
        ws_esaq = wb.Sheets("TESTE_DE_BANDA_ESAQ")

        for sh in (ws_car, ws_esaq):
            try:
                sh.Unprotect("")
            except Exception:
                try:
                    sh.Unprotect()
                except Exception:
                    pass

        merged_log_ranges = _preparar_area_logs_com(ws_car)

        for key, cell in CADERNO_CELLS.items():
            _set(ws, cell, valores_caderno.get(key))

        for field, row in CARIMBO_LINK_SAI_BL.items():
            _set(ws_car, f"D{row}", link_sai_bl.get(field))
        if link_sai_bli:
            for field, row in CARIMBO_LINK_SAI_BLI.items():
                _set(ws_car, f"D{row}", link_sai_bli.get(field))
        else:
            for row in CARIMBO_LINK_SAI_BLI.values():
                _set(ws_car, f"D{row}", "")
        for field, row in CARIMBO_LINK_SCM_MPLS.items():
            _set(ws_car, f"D{row}", link_scm.get(field))

        for cmd, body in logs_por_cmd.items():
            if cmd == "show sys interface" or cmd.startswith("show sys interface "):
                continue
            anchor = CARIMBO_CMD_ANCHOR_ROWS.get(cmd)
            if anchor:
                _paste_log_com(ws_car, anchor, body)

        if show_interface_parts:
            _paste_log_com(ws_car, CARIMBO_SHOW_INTERFACE_ANCHOR_ROW, "\n\n".join(show_interface_parts))

        for item in itens_executor_status:
            row = item.get("row")
            if not row:
                continue
            if item.get("executor"):
                _set(ws, f"D{row}", item["executor"])
            if item.get("status"):
                _set(ws, f"E{row}", item["status"])

        if portal_banda_larga_ok:
            if image_temp_path and os.path.isfile(image_temp_path):
                _inserir_imagem_esaq_com(ws_esaq, image_temp_path, ESAQ_IMAGE_CELL)
        else:
            if image_erro_bbl_path and os.path.isfile(image_erro_bbl_path):
                _inserir_imagem_esaq_com(ws_esaq, image_erro_bbl_path, ESAQ_IMAGE_CELL)
            if image_speedtest_path and os.path.isfile(image_speedtest_path):
                _inserir_imagem_esaq_com(ws_esaq, image_speedtest_path, ESAQ_IMAGE_CELL_SPEEDTEST)
            _inserir_disclaimer_portal_indisponivel_com(ws_esaq)

        _restaurar_merges_com(ws_car, merged_log_ranges)
        wb.SaveAs(temp_saida, FileFormat=_excel_file_format(temp_saida))
        gerado_ok = True
    except Exception:
        logger.exception("gerar_caderno_via_excel_com falhou")
        raise
    finally:
        _encerrar_excel_com(excel, wb)
        excel = None
        wb = None
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        if gerado_ok:
            try:
                _publicar_caderno_gerado(temp_saida, out_abs)
            except OSError:
                logger.exception("Falha ao publicar caderno gerado em %s", os.path.basename(out_abs))
                raise
        for temp in (temp_modelo, temp_saida):
            try:
                if temp and os.path.isfile(temp) and os.path.abspath(temp) != out_abs:
                    os.remove(temp)
            except OSError:
                pass
