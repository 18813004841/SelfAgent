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
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from core.storage import connect, decode_schedule, get_settings, save_settings, default_settings, PID_PATH
import subprocess, sys

PORT = int(os.environ.get("MACHINE_DASHBOARD_PORT", "18888"))

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


HTML = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
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
                data = HTML.encode("utf-8")
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
                kwargs = {}
                if os.name == "nt":
                    kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / "scheduler.py")], cwd=str(Path(__file__).resolve().parent.parent), env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent)}, **kwargs)
                self.send_json(200, {"ok": True}); return
            if path == "/api/scheduler/stop":
                pid=int(PID_PATH.read_text(encoding="utf-8"))
                if pid == os.getpid(): raise RuntimeError("refusing to stop web server process")
                if os.name == "nt": subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
                else: os.kill(pid, 15)
                PID_PATH.unlink(missing_ok=True); self.send_json(200, {"ok": True}); return
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
                data = HTML.encode("utf-8")
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








