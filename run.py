# run.py
import os
import datetime
import dotenv
from waitress import serve
from flask import Flask, g, redirect, request, url_for
from werkzeug.wsgi import LimitedStream

dotenv.load_dotenv()

MODE = 'dev'
IS_DEV = MODE == 'dev'

# ✅ PASSO 1: configura logging ANTES de qualquer blueprint
# Toda a lógica de como logar fica no core/logger.py
from core.logger import setup_logger, get_logger

setup_logger(
    name="app",
    log_file=os.path.join(os.path.dirname(__file__), 'logs', 'app.log')
)

log = get_logger("RUN")  # logger do próprio run.py

# ✅ PASSO 2: só agora importa os blueprints
from login.main       import init_login
from login.presence   import before_request_session_presence
from login.presence_config import REMEMBER_COOKIE_HOURS
from rd.app           import rd_bp
from fust.app         import fust_bp
from itau.app         import itau_bp
from sluis.app        import sluis_bp
from copa_energia.app import copa_bp
from sabesp.app       import sabesp_bp
from prodam.app       import prodam_bp
from grupo_lider.app  import grupo_lider_bp
from prateleira.app   import prateleira_bp
from core.app         import core_bp
from agendamentos.app import agendamentos_bp
from prodesp.app      import prodesp_bp
from vgr.app          import vgr_bp
from dma.app          import dma_bp

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 480 * 1024 * 1024
app.secret_key = os.getenv('FLASK_SECRET_KEY').encode('utf-8')
app.debug = IS_DEV
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(hours=REMEMBER_COOKIE_HOURS)
LimitedStream.MAX_CONTENT_LENGTH = 480 * 1024 * 1024

from core.security.http_headers import apply_session_cookie_config, register_security_headers

apply_session_cookie_config(app)
_csp_report_only = (os.getenv("PORTAL_CSP_REPORT_ONLY") or "true").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
)
register_security_headers(app, csp_report_only=_csp_report_only)

init_login(app)


@app.context_processor
def inject_portal_flash():
    from core.portal_flash import portal_flash_alert_class, portal_flashed_messages as _portal_flashed_messages

    def portal_flashed_messages(view_scope=None):
        return _portal_flashed_messages(view_scope=view_scope, endpoint=request.endpoint)

    return {
        "portal_flashed_messages": portal_flashed_messages,
        "portal_flash_alert_class": portal_flash_alert_class,
    }


@app.before_request
def portal_session_presence():
    _slow_ms = int(os.getenv("PORTAL_SLOW_REQUEST_LOG_MS") or "0")
    if _slow_ms > 0:
        import time

        g._portal_req_start = time.perf_counter()
    return before_request_session_presence()


def _portal_slow_log_skip_path(path: str) -> bool:
    """Ignora polls de alta frequência (evita encher app.log com ruído esperado)."""
    raw = (os.getenv("PORTAL_SLOW_REQUEST_LOG_SKIP_PATHS") or "").strip()
    if not raw:
        raw = "/login/api/notificacoes/count,/login/api/presence"
    prefixes = [p.strip() for p in raw.split(",") if p.strip()]
    return any(path == p or path.startswith(p + "/") for p in prefixes)


@app.after_request
def portal_slow_request_log(response):
    """Loga requisições acima de PORTAL_SLOW_REQUEST_LOG_MS (monitoramento de pico)."""
    try:
        threshold = int(os.getenv("PORTAL_SLOW_REQUEST_LOG_MS") or "0")
    except ValueError:
        return response
    if threshold <= 0:
        return response
    if _portal_slow_log_skip_path(request.path):
        return response
    start = getattr(g, "_portal_req_start", None)
    if start is None:
        return response
    import time

    elapsed_ms = (time.perf_counter() - start) * 1000
    if elapsed_ms >= threshold:
        log.warning(
            "slow request %.0fms %s %s status=%s",
            elapsed_ms,
            request.method,
            request.path,
            response.status_code,
        )
    return response


app.register_blueprint(rd_bp)
app.register_blueprint(fust_bp)
app.register_blueprint(itau_bp)
app.register_blueprint(sluis_bp)
app.register_blueprint(copa_bp)
app.register_blueprint(sabesp_bp)
app.register_blueprint(prodam_bp)
app.register_blueprint(grupo_lider_bp)
app.register_blueprint(prateleira_bp)
app.register_blueprint(core_bp)
app.register_blueprint(agendamentos_bp)
app.register_blueprint(prodesp_bp)
app.register_blueprint(vgr_bp)
app.register_blueprint(dma_bp)

# Scheduler relatório gestão PRODESP (prodesp/prodesp/gestao/)
from prodesp.prodesp.gestao.gestao_relatorio_scheduler import start_gestao_relatorio_scheduler
from prodesp.prodesp.gestao.tbra_relatorio_scheduler import start_tbra_relatorio_scheduler

start_gestao_relatorio_scheduler(app)
start_tbra_relatorio_scheduler(app)
from core.reports.scheduler import start_supervisores_relatorio_scheduler

start_supervisores_relatorio_scheduler(app)


@app.route('/')
def home():
    return redirect(url_for('login.view_login'))


if __name__ == '__main__':
    if IS_DEV:
        log.info("🔧 MODO DEV")
        app.run(host='0.0.0.0', port=8507, debug=True)
    else:
        log.info("🚀 MODO PRODUÇÃO")
        # Fila do Waitress cresce quando threads < requisições concorrentes; ajuste via WAITRESS_THREADS.
        _threads = int(os.getenv("WAITRESS_THREADS", "30"))
        serve(
            app,
            host='0.0.0.0',
            port=8507,
            threads=max(4, min(_threads, 64)),
            channel_timeout=180,
            connection_limit=1000,
            cleanup_interval=10,
            backlog=512,
            max_request_body_size=480*1024*1024,
            recv_bytes=65536,
        )
