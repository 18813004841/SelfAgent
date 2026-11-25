from pathlib import Path
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = "central-server"
logger = get_logger('central_server', DEBUG_LOG_DIR)


def _send_package_missing(request, package_name: str):
    """Return a client-visible error when an optional download artifact is absent."""
    request.send_json(404, {
        "ok": False,
        "error": f"{package_name} has not been built",
        "code": "package_not_built",
        "package": package_name,
    })

@router.route("GET", "/api/central-server/status", "/api/central-server/connections", "/api/central-client/status", "/api/central-client/version", "/api/central-client/download", "/api/local-agent/version", "/api/local-agent/download")
def handle(ctx):
    logger.debug("handling %s %s", ctx.method, ctx.path)
    import sys, time, socket
    server = sys.modules.get("server") or sys.modules["__main__"]
    if ctx.path == "/api/central-server/status":
        pid = None
        try: pid = int(server.CENTER_PID_PATH.read_text(encoding="utf-8"))
        except Exception: pass
        running = server.center_server_running(pid)
        logger.info("central_server.status.result pid=%s pid_path=%s running=%s", pid, server.CENTER_PID_PATH, running)
        if not running:
            server.CENTER_PID_PATH.unlink(missing_ok=True)
        ctx.request.send_json(200, {"ok": True, "service": "central-server", "running": running, "pid": pid, "port": server.CENTER_PORT})
    elif ctx.path == "/api/central-client/status":
        ctx.request.send_json(409, {"ok": False, "error": "中央客户端由浏览这台电脑的本地接入服务管理", "code": "client_local_only"})
    elif ctx.path == "/api/central-client/version":
        version_file = Path(__file__).resolve().parents[4] / "Tools" / "machine-control" / "client" / "client_package" / "VERSION"
        if not version_file.is_file():
            raise FileNotFoundError("central-client VERSION has not been configured")
        version = version_file.read_text(encoding="utf-8").strip()
        if not version:
            raise ValueError("central-client VERSION is empty")
        ctx.request.send_json(200, {"ok": True, "version": version})
    elif False and ctx.path == "/api/central-client/status":
        item = server.PROCESS_MANAGER.snapshot().get("central-client", {})
        storage = server.Path(server.get_settings().get("storage_dir", server.default_settings()["storage_dir"]))
        client = storage / "central-client"
        ctx.request.send_json(200, {"ok": True, "service": "central-client", "running": item.get("status") == "running", "pid": item.get("pid"), "storage_dir": str(storage), "client_dir": str(client), "client_dir_exists": client.is_dir(), "client_entry_exists": (client / "control_worker" / "client.py").is_file()})
    elif ctx.path == "/api/central-server/connections":
        from core.central_connections import get_connections
        result = get_connections(server.CENTER_PORT, getattr(server, "MACHINE_CONTROL_SERVER_URL", None))
        ctx.request.send_json(200, {"ok": True, **result})
    elif ctx.path == "/api/central-client/download":
        package = Path(__file__).resolve().parents[4] / "Tools" / "machine-control" / "packages" / "central-client.zip"
        if not package.is_file():
            _send_package_missing(ctx.request, "central-client.zip")
            return True
        data = package.read_bytes()
        ctx.request.send_response(200)
        ctx.request.send_header("Content-Type", "application/zip")
        ctx.request.send_header("Content-Disposition", 'attachment; filename="central-client.zip"')
        ctx.request.send_header("Content-Length", str(len(data)))
        ctx.request.end_headers(); ctx.request.wfile.write(data)
    elif ctx.path == "/api/local-agent/version":
        version_file = Path(__file__).resolve().parents[2].parent / "machine-dashboard-client" / "VERSION"
        if not version_file.is_file():
            raise FileNotFoundError("workbench local-agent VERSION has not been configured")
        version = version_file.read_text(encoding="utf-8").strip()
        if not version:
            raise ValueError("workbench local-agent VERSION is empty")
        ctx.request.send_json(200, {"ok": True, "service": "workbench-local-agent", "version": version})
    elif ctx.path == "/api/local-agent/download":
        package = Path(__file__).resolve().parents[2].parent / "machine-dashboard-client" / "dist" / "workbench-machine-dashboard-client.zip"
        if not package.is_file():
            _send_package_missing(ctx.request, "workbench-machine-dashboard-client.zip")
            return True
        data = package.read_bytes()
        ctx.request.send_response(200); ctx.request.send_header("Content-Type", "application/zip")
        ctx.request.send_header("Content-Disposition", 'attachment; filename="workbench-machine-dashboard-client.zip"')
        ctx.request.send_header("Content-Length", str(len(data))); ctx.request.end_headers(); ctx.request.wfile.write(data)
    return True

