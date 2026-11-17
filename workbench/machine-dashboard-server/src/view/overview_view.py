from pathlib import Path
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'src/process_manager/logs'
logger = get_logger('overview', DEBUG_LOG_DIR)

@router.route("GET", "/api/health", "/api/processes", "/api/machines", "/api/machine/*")
@router.route("POST", "/api/central-server/start", "/api/central-server/stop", "/api/central-server/cleanup", "/api/central-client/start", "/api/central-client/stop")
def handle(ctx):
    logger.debug("handling %s %s", ctx.method, ctx.path)
    import sys
    server = sys.modules.get("server") or sys.modules["__main__"]
    if ctx.path == "/api/health": ctx.request.send_json(200, {"ok": True, "service": "machine-dashboard-server", "mode": "local"})
    elif ctx.path == "/api/processes": ctx.request.send_json(200, {"ok": True, "processes": server.PROCESS_MANAGER.snapshot()})
    elif ctx.path == "/api/machines": ctx.request.send_json(200, {"ok": True, "machines": [server.local_machine()], "mode": "local"})
    elif ctx.path.startswith("/api/machine/") and ctx.path.endswith("/metrics"):
        mid = ctx.path[len("/api/machine/"):-len("/metrics")]; ctx.request.send_json(200, {"ok": True, "machine_id": mid, "metrics": server.local_metrics()})
    elif ctx.path == "/api/central-server/start":
        server.MACHINE_CONTROL_ROOT.mkdir(parents=True, exist_ok=True); h = server.PROCESS_MANAGER.start("central-server"); ctx.request.send_json(200, {"ok": True, "pid": h.pid})
    elif ctx.path == "/api/central-server/stop": server.PROCESS_MANAGER.stop("central-server"); ctx.request.send_json(200, {"ok": True})
    elif ctx.path == "/api/central-server/cleanup": ctx.request.send_json(200, {"ok": True, "port": server.CENTER_PORT, "killed": server.PROCESS_MANAGER.cleanup("central-server")})
    elif ctx.path == "/api/central-client/start": ctx.request.send_json(409, {"ok": False, "error": "中央客户端由浏览这台电脑的本地接入服务管理", "code": "client_local_only"})
    elif False and ctx.path == "/api/central-client/start": h=server.PROCESS_MANAGER.start("central-client"); ctx.request.send_json(200, {"ok": True, "pid": h.pid})
    elif ctx.path == "/api/central-client/stop": ctx.request.send_json(409, {"ok": False, "error": "中央客户端由浏览这台电脑的本地接入服务管理", "code": "client_local_only"})
    elif False and ctx.path == "/api/central-client/stop": server.PROCESS_MANAGER.stop("central-client"); ctx.request.send_json(200, {"ok": True})
    return True



