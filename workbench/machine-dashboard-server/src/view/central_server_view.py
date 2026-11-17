from pathlib import Path
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = "central-server"
logger = get_logger('central_server', DEBUG_LOG_DIR)

@router.route("GET", "/api/central-server/status", "/api/central-server/connections", "/api/central-client/status", "/api/central-client/download", "/api/local-agent/download")
def handle(ctx):
    logger.debug("handling %s %s", ctx.method, ctx.path)
    import sys, time, socket
    server = sys.modules.get("server") or sys.modules["__main__"]
    if ctx.path == "/api/central-server/status":
        pid = None
        try: pid = int(server.CENTER_PID_PATH.read_text(encoding="utf-8"))
        except Exception: pass
        running = server.center_server_running(pid)
        if not running:
            server.CENTER_PID_PATH.unlink(missing_ok=True)
        ctx.request.send_json(200, {"ok": True, "service": "central-server", "running": running, "pid": pid, "port": server.CENTER_PORT})
    elif ctx.path == "/api/central-client/status":
        ctx.request.send_json(409, {"ok": False, "error": "中央客户端由浏览这台电脑的本地接入服务管理", "code": "client_local_only"})
    elif False and ctx.path == "/api/central-client/status":
        item = server.PROCESS_MANAGER.snapshot().get("central-client", {})
        storage = server.Path(server.get_settings().get("storage_dir", server.default_settings()["storage_dir"]))
        client = storage / "central-client"
        ctx.request.send_json(200, {"ok": True, "service": "central-client", "running": item.get("status") == "running", "pid": item.get("pid"), "storage_dir": str(storage), "client_dir": str(client), "client_dir_exists": client.is_dir(), "client_entry_exists": (client / "control_worker" / "client.py").is_file()})
    elif ctx.path == "/api/central-server/connections":
        import json, os, time, urllib.request
        base = f"http://127.0.0.1:{server.CENTER_PORT}"
        try:
            request = urllib.request.Request(base + "/api/workers", headers={"Authorization": f"Bearer {os.environ.get('MACHINE_CONTROL_TOKEN', 'dev-token')}"})
            with urllib.request.urlopen(request, timeout=0.8) as response:
                workers = json.loads(response.read().decode("utf-8")).get("workers", [])
            ips = []
            for worker in workers:
                last_seen = worker.get("last_seen_at", 0) or 0
                if worker.get("status") != "online" or (time.time() * 1000 - last_seen) >= 45000: continue
                for ip in worker.get("meta", {}).get("local_ips", []):
                    if ip and ip not in ips and not ip.startswith("127."): ips.append(ip)
            ctx.request.send_json(200, {"ok": True, "ips": ips, "workers": workers})
        except Exception:
            ctx.request.send_json(200, {"ok": True, "ips": [], "workers": [], "available": False})
    elif ctx.path == "/api/central-client/download":
        package = Path(__file__).resolve().parents[4] / "Tools" / "machine-control" / "packages" / "central-client.zip"
        if not package.is_file():
            raise FileNotFoundError("central-client.zip has not been built")
        data = package.read_bytes()
        ctx.request.send_response(200)
        ctx.request.send_header("Content-Type", "application/zip")
        ctx.request.send_header("Content-Disposition", 'attachment; filename="central-client.zip"')
        ctx.request.send_header("Content-Length", str(len(data)))
        ctx.request.end_headers(); ctx.request.wfile.write(data)
    elif ctx.path == "/api/local-agent/download":
        package = Path(__file__).resolve().parents[2].parent / "machine-dashboard-client" / "dist" / "workbench-machine-dashboard-client.zip"
        if not package.is_file():
            raise FileNotFoundError("workbench-machine-dashboard-client.zip has not been built")
        data = package.read_bytes()
        ctx.request.send_response(200); ctx.request.send_header("Content-Type", "application/zip")
        ctx.request.send_header("Content-Disposition", 'attachment; filename="workbench-machine-dashboard-client.zip"')
        ctx.request.send_header("Content-Length", str(len(data))); ctx.request.end_headers(); ctx.request.wfile.write(data)
    return True

