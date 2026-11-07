#!/usr/bin/env python3
"""独立运行的本地工作台 HTTP 服务。

服务提供单页工作台界面，并暴露进程管理、工具、定时任务、设置和报告等
本地 JSON 接口。长时间任务交给受管进程或调度器执行，请求处理器负责校验
输入、更新持久化数据并尽快返回。
"""
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
from launchers.openai_agent import OpenAIAgentLauncher
from schedulers.code_review_scheduler import start_task, stop_task, task_payload, update_task_config

# 工作台 HTTP 端口。所有服务端口均可通过环境变量配置，避免本地服务冲突。
PORT = int(os.environ.get("MACHINE_DASHBOARD_PORT", "18888"))
HOST = os.environ.get("MACHINE_DASHBOARD_HOST", "127.0.0.1").strip().strip('"') or "0.0.0.0"
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
PROCESS_MANAGER.register(OpenAIAgentLauncher(Path(__file__).resolve().parents[3] / "AiAgent" / "AiProject" / "Codes" / "Agents" / "OpenAiAgent", int(os.environ.get("CODEX_GATEWAY_PORT", "8765"))))
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

def clear_port(port: int) -> list[int]:
    """结束当前监听指定本地端口的 Windows 进程。"""
    killed = []
    if os.name != "nt":
        return killed
    output = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[0].upper() == "TCP" and fields[1].endswith(f":{port}") and fields[3].upper() == "LISTENING":
            try:
                pid = int(fields[4])
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                killed.append(pid)
            except ValueError:
                continue
    return killed


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
    """处理工作台页面和本地 JSON 接口的 HTTP 请求。"""
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
        """分发会修改数据的接口，并返回 JSON 结果。"""
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
            if path == "/api/central-server/cleanup":
                killed = PROCESS_MANAGER.cleanup("central-server")
                self.send_json(200, {"ok": True, "port": CENTER_PORT, "killed": killed}); return
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
            if path == "/api/openai-agent/start":
                OPERATION_LOG.info("api.openai_agent.start")
                handle = PROCESS_MANAGER.start("openai-agent")
                self.send_json(200, {"ok": True, "pid": handle.pid, "port": handle.port}); return
            if path == "/api/openai-agent/stop":
                OPERATION_LOG.info("api.openai_agent.stop")
                PROCESS_MANAGER.stop("openai-agent")
                self.send_json(200, {"ok": True}); return
            if path == "/api/openai-agent/cleanup":
                killed = PROCESS_MANAGER.cleanup("openai-agent")
                self.send_json(200, {"ok": True, "port": int(os.environ.get("CODEX_GATEWAY_PORT", "8765")), "killed": killed}); return
            if path == "/api/openai-agent/chat":
                message = str(body.get("message", "")).strip()
                if not message: raise ValueError("message is required")
                answer = PROCESS_MANAGER._entry("openai-agent").process.chat(message, str(body.get("model") or "gpt-5.6-terra"))
                self.send_json(200, {"ok": True, "answer": answer}); return
            db = connect()
            if path == "/api/scheduler-tasks/code-review/run":
                self.send_json(200, {"ok": True, "task": start_task(str(body.get("project_path", "")), str(body.get("branch", "")), body.get("skill_paths", ["skills"]), bool(body.get("allow_extra_rules", False)), str(body.get("failure_threshold", "high")))}); return
            if path == "/api/scheduler-tasks/code-review/stop":
                self.send_json(200, {"ok": True, "task": stop_task()}); return
            if path == "/api/scheduler-tasks/code-review/config":
                self.send_json(200, {"ok": True, "task": update_task_config(str(body.get("project_path", "")), str(body.get("branch", "")), body.get("skill_paths", ["skills"]), bool(body.get("allow_extra_rules", False)), str(body.get("failure_threshold", "high")))}); return
            if path == "/api/scheduler-tasks/code-review/choose":
                import tkinter as tk
                from tkinter import filedialog
                current = str(body.get("current_path") or task_payload().get("project_path") or (Path.home() / "Desktop"))
                root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
                selected = filedialog.askdirectory(title="选择工程目录", initialdir=current if Path(current).is_dir() else str(Path.home()))
                root.destroy()
                self.send_json(200, {"ok": True, "project_path": str(Path(selected).resolve()) if selected else ""}); return
            if path == "/api/scheduler-tasks/code-review/open":
                target = Path(str(body.get("project_path", "")).strip()).expanduser()
                if not target.is_dir(): raise ValueError("工程目录不存在")
                os.startfile(target)
                self.send_json(200, {"ok": True}); return
            if path == "/api/code-review/setup":
                project_path = str(body.get("project_path", "")).strip()
                if not project_path: raise ValueError("project_path is required")
                tool_id = str(body.get("tool_id", "code-review-agent"))
                entry = str(Path(__file__).resolve().parents[3] / "Tools" / "code-review-agent" / "run_task.py")
                db.execute("INSERT OR REPLACE INTO tools(tool_id,name,type,entry,workdir,enabled) VALUES(?,?,?,?,?,1)", (tool_id, "Unity 代码检查 Agent", "local_process", entry, str(Path(entry).parent)))
                schedule_id = str(body.get("schedule_id", "code-review-daily"))
                args = {"project_path": project_path, "branch": body.get("branch", "main"), "skill_paths": body.get("skill_paths", ["skills"]), "config_path": body.get("config_path")}
                db.execute("INSERT OR REPLACE INTO schedules(id,name,tool_id,schedule_type,schedule_expr,args_json,timeout,retry,enabled,next_run,task_type,dispatcher,progress_total) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (schedule_id, body.get("name", "Unity 代码每日检查"), tool_id, "daily", body.get("time", "04:00"), json.dumps(args, ensure_ascii=False), int(body.get("timeout", 900)), 0, 1, time.time(), "scheduled", "scheduler", 5))
                db.commit(); self.send_json(201, {"ok": True, "tool_id": tool_id, "schedule_id": schedule_id, "schedule_type": "daily", "schedule_expr": body.get("time", "04:00")}); return
            if path == "/api/tools":
                db.execute("INSERT OR REPLACE INTO tools(tool_id,name,type,entry,workdir,enabled) VALUES(?,?,?,?,?,?)", (body["tool_id"], body.get("name", body["tool_id"]), body.get("type", "local_process"), body["entry"], body.get("workdir"), int(body.get("enabled", True))))
                db.commit(); self.send_json(201, {"ok": True, "tool_id": body["tool_id"]}); return
            if path == "/api/scheduler-tasks":
                self.send_json(200, {"ok": True, "tasks": [task_payload()]}); return
            if path == "/api/scheduler-tasks/code-review":
                self.send_json(200, {"ok": True, "task": task_payload()}); return
            if path == "/api/schedules":
                sid = body.get("id") or str(int(time.time() * 1000))
                db.execute("INSERT INTO schedules(id,name,tool_id,schedule_type,schedule_expr,args_json,timeout,retry,enabled,next_run,task_type,dispatcher,progress_total) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (sid, body["name"], body["tool_id"], body.get("schedule_type", "interval"), body.get("schedule_expr", "60"), json.dumps(body.get("args", {}), ensure_ascii=False), int(body.get("timeout", 300)), int(body.get("retry", 0)), int(body.get("enabled", True)), time.time(), body.get("task_type", "scheduled"), body.get("dispatcher", "scheduler"), int(body.get("progress_total", 1))))
                db.commit(); self.send_json(201, {"ok": True, "id": sid}); return
            if path.startswith("/api/schedules/") and path.endswith("/cancel"):
                sid = urllib.parse.unquote(path[len("/api/schedules/"):-len("/cancel")])
                OPERATION_LOG.info("[feature=scheduler] api.schedule.cancel id=%s", sid)
                db.execute("UPDATE schedules SET cancel_requested=1,last_status='cancelling' WHERE id=?", (sid,)); db.commit(); self.send_json(200, {"ok": True, "id": sid}); return
            if path.startswith("/api/schedules/") and path.endswith(("/enable", "/disable")):
                sid = path.split("/")[-2]; enabled = 1 if path.endswith("/enable") else 0
                db.execute("UPDATE schedules SET enabled=? WHERE id=?", (enabled, sid)); db.commit(); self.send_json(200, {"ok": True, "enabled": bool(enabled)}); return
            self.send_json(404, {"ok": False, "error": "not found"})
        except Exception as exc:
            self.send_json(400, {"ok": False, "error": repr(exc)})

    def do_GET(self):
        """返回静态页面或只读接口数据。"""
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
            if path == "/api/scheduler-tasks":
                self.send_json(200, {"ok": True, "tasks": [task_payload()]}); return
            if path == "/api/scheduler-tasks/code-review":
                self.send_json(200, {"ok": True, "task": task_payload()}); return
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
            if path.startswith("/api/schedules/"):
                sid = urllib.parse.unquote(path[len("/api/schedules/"):])
                db = connect(); row = db.execute("SELECT s.*, t.name tool_name, t.type tool_type FROM schedules s LEFT JOIN tools t ON t.tool_id=s.tool_id WHERE s.id=?", (sid,)).fetchone()
                if not row: self.send_json(404, {"ok": False, "error": "schedule not found"}); return
                item = decode_schedule(row); item["runs"] = [dict(x) for x in db.execute("SELECT * FROM runs WHERE schedule_id=? ORDER BY id DESC LIMIT 30", (sid,))]; self.send_json(200, {"schedule": item}); return
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
            if path == "/api/openai-agent/status":
                item = PROCESS_MANAGER.snapshot().get("openai-agent", {})
                project_dir = Path(__file__).resolve().parents[3] / "AiAgent" / "AiProject" / "Codes" / "Agents" / "OpenAiAgent"
                self.send_json(200, {"ok": True, "service": "openai-agent", "running": item.get("status") == "running", "pid": item.get("pid"), "port": item.get("port"), "project_dir": str(project_dir), "entry_exists": (project_dir / "codex_agent" / "openai_gateway.py").is_file()}); return
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
    OPERATION_LOG.info("[feature=machine-dashboard] server.started url=http://%s:%s mode=local-only", HOST, PORT)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        OPERATION_LOG.info("[feature=machine-dashboard] server.stopped")








