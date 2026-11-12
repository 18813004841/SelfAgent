from pathlib import Path
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'src/process_manager/logs'
logger = get_logger('central_server', DEBUG_LOG_DIR)

@router.route("GET", "/api/central-server/status", "/api/central-server/connections", "/api/central-client/status")
def handle(ctx):
    logger.debug("handling %s %s", ctx.method, ctx.path)
    import sys, time, socket
    server = sys.modules.get("server") or sys.modules["__main__"]
    if ctx.path == "/api/central-server/status":
        pid = None
        try: pid = int(server.CENTER_PID_PATH.read_text(encoding="utf-8"))
        except Exception: pass
        running = server.center_server_running(pid)
        ctx.request.send_json(200, {"ok": True, "service": "central-server", "running": running, "pid": pid, "port": server.CENTER_PORT})
    elif ctx.path == "/api/central-client/status":
        item = server.PROCESS_MANAGER.snapshot().get("central-client", {})
        storage = server.Path(server.get_settings().get("storage_dir", server.default_settings()["storage_dir"]))
        client = storage / "central-client"
        ctx.request.send_json(200, {"ok": True, "service": "central-client", "running": item.get("status") == "running", "pid": item.get("pid"), "storage_dir": str(storage), "client_dir": str(client), "client_dir_exists": client.is_dir(), "client_entry_exists": (client / "control_worker" / "client.py").is_file()})
    elif ctx.path == "/api/central-server/connections":
        ctx.request.send_json(200, {"ok": True, "ips": [], "workers": [], "available": False})
    return True



