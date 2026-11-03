#!/usr/bin/env python3
"""Standalone local machine dashboard server."""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core.storage import connect, decode_schedule, get_settings, save_settings, default_settings, PID_PATH
from process_manager import ProcessManager
from process_manager.operation_log import get_operation_logger
import subprocess, sys
import mimetypes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from launchers.central_server import CentralServerLauncher
from launchers.scheduler import SchedulerLauncher
from launchers.worker_client import WorkerClientLauncher

PORT = int(os.environ.get("MACHINE_DASHBOARD_PORT", "18888"))
MACHINE_CONTROL_ROOT = Path(__file__).resolve().parents[3] / "Tools" / "machine-control"
CENTER_PID_PATH = Path(__file__).resolve().parent.parent / "data" / "central-server.pid"
CENTER_PORT = int(os.environ.get("MACHINE_CONTROL_PORT", "18765"))
PROCESS_MANAGER = ProcessManager()
PROCESS_MANAGER.register(CentralServerLauncher(MACHINE_CONTROL_ROOT, CENTER_PORT, CENTER_PID_PATH))
PROCESS_MANAGER.register(SchedulerLauncher(Path(__file__).resolve().parent / "scheduler.py", PID_PATH))
PROCESS_MANAGER.register(WorkerClientLauncher(
    MACHINE_CONTROL_ROOT,
    lambda: get_settings().get("storage_dir", default_settings()["storage_dir"]),
    os.environ.get("MACHINE_CONTROL_SERVER_URL", f"http://127.0.0.1:{CENTER_PORT}"),
    os.environ.get("MACHINE_CONTROL_TOKEN", "dev-token"),
))
OPERATION_LOG = get_operation_logger()

def process_exists(pid):
    if not pid: return False
    try:
        if os.name == "nt":
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            return f'"{pid}"' in result.stdout
        os.kill(pid, 0); return True
    except Exception:
        return False


def local_metrics():
    memory = {"error": "memory metrics unavailable"}
    try:
        import psutil
        vm = psutil.virtual_memory()
        memory = {"total": vm.total, "available": vm.available, "used": vm.used,
                  "percent": vm.percent, "source": "psutil"}
    except Exception:
        if platform.system() == "Windows":
            try:
                import ctypes
                class MemoryStatusEx(ctypes.Structure):
                    _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                                ("total_phys", ctypes.c_ulonglong), ("avail_phys", ctypes.c_ulonglong),
                                ("total_page", ctypes.c_ulonglong), ("avail_page", ctypes.c_ulonglong),
                                ("total_virtual", ctypes.c_ulonglong), ("avail_virtual", ctypes.c_ulonglong),
                                ("avail_extended", ctypes.c_ulonglong)]
                status = MemoryStatusEx()
                status.length = ctypes.sizeof(status)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
                used = status.total_phys - status.avail_phys
                memory = {"total": status.total_phys, "available": status.avail_phys,
                          "used": used, "percent": status.memory_load, "source": "windows"}
            except Exception as exc:
                memory = {"error": repr(exc)}

    disks = []
    for path in (["C:\\"] if os.name == "nt" else ["/"]):
        try:
            usage = shutil.disk_usage(path)
            percent = round(usage.used * 100 / usage.total, 1) if usage.total else 0
            disks.append({"mount": path, "total": usage.total, "used": usage.used,
                          "free": usage.free, "percent": percent})
        except Exception:
            pass

    hostname = socket.gethostname()
    ips = []
    try:
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = item[4][0]
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return {"hostname": hostname, "os": platform.platform(), "system": platform.system(),
            "ips": ips, "memory": memory, "disks": disks,
            "timestamp": int(time.time())}


def local_machine():
    metrics = local_metrics()
    return {"machine_id": metrics["hostname"], "worker_id": metrics["hostname"],
            "hostname": metrics["hostname"], "os": metrics["os"],
            "status": "local", "login_state": "local", "current_ips": metrics["ips"]}

def center_server_running(pid=None):
    if pid is not None and not process_exists(pid):
        return False
    try:
        with socket.create_connection(("127.0.0.1", CENTER_PORT), timeout=0.35):
            return True
    except OSError:
        return False


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"

def index_html():
    return (WEB_ROOT / "index.html").read_text(encoding="utf-8")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {self.client_address[0]} {fmt % args}", flush=True)

    def send_json(self, code: int, value):
        data = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_POST(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/" or path == "/index.html":
                data = index_html().encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            if path.startswith("/pages/") or path.startswith("/assets/"):
                file_path = (Path(__file__).resolve().parent.parent / "web" / path.lstrip("/")).resolve()
                web_root = (Path(__file__).resolve().parent.parent / "web").resolve()
                if file_path.is_file() and str(file_path).startswith(str(web_root)):
                    data = file_path.read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8" if file_path.suffix == ".html" else "text/css" if file_path.suffix == ".css" else "application/javascript"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            body = self.read_body()
            if path == "/api/settings/storage/choose":
                import tkinter as tk
                from tkinter import filedialog
                current = get_settings().get("storage_dir", default_settings()["storage_dir"])
                root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
                selected = filedialog.askdirectory(title="选择本地文件保存目录", initialdir=current if Path(current).exists() else str(Path.home()))
                root.destroy()
                if selected:
                    save_settings({"storage_dir": str(Path(selected).resolve())})
                self.send_json(200, {"ok": True, "selected": bool(selected), "settings": get_settings()}); return
            if path == "/api/settings/storage":
                value = str(body.get("storage_dir", "")).strip()
                if not value: raise ValueError("storage_dir is required")
                save_settings({"storage_dir": str(Path(value).expanduser().resolve())})
                self.send_json(200, {"ok": True, "settings": get_settings()}); return
            if path == "/api/settings/storage/reset":
                save_settings(default_settings()); self.send_json(200, {"ok": True, "settings": get_settings()}); return
            if path == "/api/scheduler/start":
                OPERATION_LOG.info("api.scheduler.start")
                handle = PROCESS_MANAGER.start("scheduler")
                self.send_json(200, {"ok": True, "pid": handle.pid}); return
            if path == "/api/central-server/start":
                OPERATION_LOG.info("api.central_server.start")
                MACHINE_CONTROL_ROOT.mkdir(parents=True, exist_ok=True)
                if PROCESS_MANAGER.status("central-server").value == "running":
                    self.send_json(200, {"ok": True, "already_running": True}); return
                handle = PROCESS_MANAGER.start("central-server")
                self.send_json(200, {"ok": True, "pid": handle.pid}); return
            if path == "/api/central-server/stop":
                OPERATION_LOG.info("api.central_server.stop")
                PROCESS_MANAGER.stop("central-server")
                self.send_json(200, {"ok": True}); return
            if path == "/api/central-client/start":
                handle = PROCESS_MANAGER.start("central-client")
                self.send_json(200, {"ok": True, "pid": handle.pid}); return
            if path == "/api/central-client/stop":
                PROCESS_MANAGER.stop("central-client")
                self.send_json(200, {"ok": True}); return
            if path == "/api/scheduler/stop":
                OPERATION_LOG.info("api.scheduler.stop")
                PROCESS_MANAGER.stop("scheduler")
                self.send_json(200, {"ok": True}); return
            db = connect()
            if path == "/api/tools":
                db.execute("INSERT OR REPLACE INTO tools(tool_id,name,type,entry,workdir,enabled) VALUES(?,?,?,?,?,?)", (body["tool_id"], body.get("name", body["tool_id"]), body.get("type", "local_process"), body["entry"], body.get("workdir"), int(body.get("enabled", True))))
                db.commit(); self.send_json(201, {"ok": True, "tool_id": body["tool_id"]}); return
            if path == "/api/schedules":
                sid = body.get("id") or str(int(time.time() * 1000))
                db.execute("INSERT INTO schedules(id,name,tool_id,schedule_type,schedule_expr,args_json,timeout,retry,enabled,next_run) VALUES(?,?,?,?,?,?,?,?,?,?)", (sid, body["name"], body["tool_id"], body.get("schedule_type", "interval"), body.get("schedule_expr", "60"), json.dumps(body.get("args", {}), ensure_ascii=False), int(body.get("timeout", 300)), int(body.get("retry", 0)), int(body.get("enabled", True)), time.time()))
                db.commit(); self.send_json(201, {"ok": True, "id": sid}); return
            if path.startswith("/api/schedules/") and path.endswith(("/enable", "/disable")):
                sid = path.split("/")[-2]; enabled = 1 if path.endswith("/enable") else 0
                db.execute("UPDATE schedules SET enabled=? WHERE id=?", (enabled, sid)); db.commit(); self.send_json(200, {"ok": True, "enabled": bool(enabled)}); return
            self.send_json(404, {"ok": False, "error": "not found"})
        except Exception as exc:
            self.send_json(400, {"ok": False, "error": repr(exc)})

    def do_GET(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                data = index_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path.startswith("/pages/") or path.startswith("/assets/"):
                web_root = (Path(__file__).resolve().parent.parent / "web").resolve()
                file_path = (web_root / path.lstrip("/")).resolve()
                if not file_path.is_file() or not str(file_path).startswith(str(web_root)):
                    self.send_json(404, {"ok": False, "error": "static file not found"}); return
                data = file_path.read_bytes()
                content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}.get(file_path.suffix, "application/octet-stream")
                self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            if path == "/api/health":
                self.send_json(200, {"ok": True, "service": "machine-dashboard-server", "mode": "local"})
                return
            if path == "/api/processes":
                self.send_json(200, {"processes": PROCESS_MANAGER.snapshot()}); return
            if path == "/api/settings/storage":
                self.send_json(200, {"ok": True, "settings": get_settings(), "default": default_settings()["storage_dir"]}); return
            if path == "/api/tools":
                db = connect(); self.send_json(200, {"tools": [dict(x) for x in db.execute("SELECT * FROM tools ORDER BY name") ]}); return
            if path == "/api/schedules":
                db = connect(); self.send_json(200, {"schedules": [decode_schedule(x) for x in db.execute("SELECT * FROM schedules ORDER BY name") ]}); return
            if path == "/api/scheduler/status":
                running=PID_PATH.exists(); pid=None
                try: pid=int(PID_PATH.read_text(encoding="utf-8"))
                except Exception: running=False
                running = process_exists(pid)
                if not running: PID_PATH.unlink(missing_ok=True)
                self.send_json(200, {"ok": True, "service": "scheduler", "mode": "separate-process", "running": running, "pid": pid}); return
            if path == "/api/central-server/status":
                pid = None
                try: pid = int(CENTER_PID_PATH.read_text(encoding="utf-8"))
                except (OSError, ValueError): pass
                running = center_server_running(pid)
                if not running: CENTER_PID_PATH.unlink(missing_ok=True)
                self.send_json(200, {"ok": True, "service": "central-server", "running": running, "pid": pid, "port": CENTER_PORT}); return
            if path == "/api/central-client/status":
                item = PROCESS_MANAGER.snapshot().get("central-client", {})
                storage_dir = Path(get_settings().get("storage_dir", default_settings()["storage_dir"]))
                client_dir = storage_dir / "central-client"
                self.send_json(200, {"ok": True, "service": "central-client", "running": item.get("status") == "running", "pid": item.get("pid"), "storage_dir": str(storage_dir), "client_dir": str(client_dir), "client_dir_exists": client_dir.is_dir(), "client_entry_exists": (client_dir / "control_worker" / "client.py").is_file()}); return
            if path == "/api/settings/storage/open":
                storage_dir = Path(get_settings().get("storage_dir", default_settings()["storage_dir"]))
                storage_dir.mkdir(parents=True, exist_ok=True)
                if os.name == "nt": os.startfile(str(storage_dir))
                elif platform.system() == "Darwin": subprocess.Popen(["open", str(storage_dir)])
                else: subprocess.Popen(["xdg-open", str(storage_dir)])
                self.send_json(200, {"ok": True, "storage_dir": str(storage_dir)}); return
            if path == "/api/central-client/download":
                package = Path(__file__).resolve().parents[3] / "Tools" / "machine-control" / "packages" / "central-client.zip"
                if not package.is_file(): raise FileNotFoundError("central-client.zip has not been built")
                data = package.read_bytes()
                self.send_response(200); self.send_header("Content-Type", "application/zip"); self.send_header("Content-Disposition", 'attachment; filename="central-client.zip"'); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            if path == "/api/central-server/connections":
                base = f"http://127.0.0.1:{CENTER_PORT}"
                def center_get(endpoint):
                    request = urllib.request.Request(base + endpoint, headers={"Authorization": f"Bearer {os.environ.get('MACHINE_CONTROL_TOKEN', 'dev-token')}"})
                    with urllib.request.urlopen(request, timeout=0.8) as response:
                        return json.loads(response.read().decode("utf-8"))
                try:
                    workers = center_get("/api/workers").get("workers", [])
                    ips = []
                    for worker in workers:
                        last_seen = worker.get("last_seen_at", 0) or 0
                        online = worker.get("status") == "online" and (time.time() * 1000 - last_seen) < 45000
                        if not online:
                            continue
                        for ip in worker.get("meta", {}).get("local_ips", []):
                            if ip and ip not in ips and not ip.startswith("127."):
                                ips.append(ip)
                    self.send_json(200, {"ok": True, "ips": ips, "workers": workers})
                except Exception:
                    self.send_json(200, {"ok": True, "ips": [], "workers": [], "available": False})
                return
            if path == "/api/machines":
                self.send_json(200, {"machines": [local_machine()], "mode": "local"})
                return
            if path.startswith("/api/machine/") and path.endswith("/metrics"):
                machine_id = urllib.parse.unquote(path[len("/api/machine/"):-len("/metrics")])
                self.send_json(200, {"ok": True, "machine_id": machine_id, "metrics": local_metrics()})
                return
            self.send_json(404, {"ok": False, "error": "not found"})
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": repr(exc), "trace": traceback.format_exc()[-2000:]})


def main():
    print(f"Machine dashboard server listening on http://127.0.0.1:{PORT}", flush=True)
    print("Mode: local-only", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Machine dashboard server stopped.", flush=True)








