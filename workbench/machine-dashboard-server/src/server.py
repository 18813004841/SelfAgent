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
from datetime import datetime

# 每次工作台启动生成新会话；必须早于所有业务和日志模块的导入。
START_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
os.environ["LOCAL_WORKBENCH_START_TIMESTAMP"] = START_TIMESTAMP

from core.storage import decode_schedule, get_settings, save_settings, default_settings, PID_PATH, CENTER_PID_PATH, MACHINE_CONTROL_STORE_PATH
from core.repositories import ScheduleRepository
from core.settings import load_local_settings
from core.Log import AppLogger
from process_manager import ProcessManager
from process_manager.operation_log import get_operation_logger
import subprocess, sys
import mimetypes
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from launchers.central_server import CentralServerLauncher
from launchers.scheduler import SchedulerLauncher
from launchers.worker_client import WorkerClientLauncher
from launchers.openai_agent import OpenAIAgentLauncher
from launchers.local_codex import LocalCodexLauncher
from schedulers.code_review_scheduler import CodeReviewScheduler, start_task, stop_task, task_payload, update_task_config
from schedulers.scheduler_controller import SchedulerController
from view import router as view_router, ViewContext
from view import routes as _view_routes
from core.auth import ensure_admin, login, current, logout, _hash_password, has_module
from core.permissions import MODULES, ALL_MODULES, ROLES, module_for_path, role_at_least, modules_for_role

# 工作台 HTTP 端口。所有服务端口均可通过环境变量配置，避免本地服务冲突。
PORT = int(os.environ.get("MACHINE_DASHBOARD_PORT", "18888"))
# The workbench is a LAN service by default; set MACHINE_DASHBOARD_HOST to
# 127.0.0.1 for an explicitly local-only deployment.
HOST = os.environ.get("MACHINE_DASHBOARD_HOST", "0.0.0.0").strip().strip('"') or "0.0.0.0"
MACHINE_CONTROL_ROOT = Path(__file__).resolve().parents[3] / "Tools" / "machine-control"
CENTER_PORT = int(os.environ.get("MACHINE_CONTROL_PORT", "18765"))
PROCESS_MANAGER = ProcessManager()
PROCESS_MANAGER.register(CentralServerLauncher(MACHINE_CONTROL_ROOT, CENTER_PORT, CENTER_PID_PATH, MACHINE_CONTROL_STORE_PATH))
PROCESS_MANAGER.register(SchedulerLauncher(Path(__file__).resolve().parent / "scheduler.py", PID_PATH))
PROCESS_MANAGER.register(WorkerClientLauncher(
    MACHINE_CONTROL_ROOT,
    lambda: get_settings().get("storage_dir", default_settings()["storage_dir"]),
    os.environ.get("MACHINE_CONTROL_SERVER_URL", f"http://127.0.0.1:{CENTER_PORT}"),
    os.environ.get("MACHINE_CONTROL_TOKEN", "dev-token"),
))
PROCESS_MANAGER.register(OpenAIAgentLauncher(Path(__file__).resolve().parents[3] / "AiAgent" / "AiProject" / "Codes" / "Agents" / "OpenAiAgent", int(os.environ.get("CODEX_GATEWAY_PORT", "8765"))))
PROCESS_MANAGER.register(LocalCodexLauncher(Path(__file__).resolve().parent.parent, int(os.environ.get("CODEX_APP_SERVER_PORT", "4500"))))
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

def standalone_auth_html(kind):
    title = "登录" if kind == "login" else "注册账号"
    page = (WEB_ROOT / "pages" / f"{kind}.html").read_text(encoding="utf-8")
    script = f'<script type="module">import {{ mount }} from "/assets/js/pages/{kind}.js?v=2"; mount();</script>'
    return f'<!doctype html><html><head><meta charset="utf-8"><title>{title} - 工作台</title><link rel="stylesheet" href="/assets/css/app.css?v=18"></head><body><main>{page}</main>{script}</body></html>'

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

    def _token(self):
        raw = self.headers.get("Cookie", "")
        for item in raw.split(";"):
            if item.strip().startswith("workbench_session="): return item.strip().split("=", 1)[1]
        return None
    def _auth(self, path):
        if path.startswith("/api/auth/") or path in ("/", "/index.html", "/pages/login.html", "/pages/register.html") or path.startswith("/assets/"):
            return None
        user = current(self._token())
        if not user: self.send_json(401, {"ok": False, "code": "unauthorized", "error": "请先登录"}); return False
        module = module_for_path(path)
        if module == "users":
            if not role_at_least(user, "admin"):
                self.send_json(403, {"ok": False, "error": "仅管理员可管理用户"}); return False
            module = "manage"
        if module and module not in user["modules"]: self.send_json(403, {"ok": False, "code": "forbidden", "error": "没有该功能权限"}); return False
        if path.startswith("/api/users") and not user["is_admin"]: self.send_json(403, {"ok": False, "code": "forbidden", "error": "仅管理员可管理用户"}); return False
        self.current_user = user
        return user

    def read_body(self):
        cached = getattr(self, "_request_body", None)
        if cached is not None:
            return cached
        length = int(self.headers.get("Content-Length", "0"))
        self._request_body = json.loads(self.rfile.read(length) or b"{}")
        return self._request_body

    def do_PATCH(self):
        return self.do_POST()

    def do_POST(self):
        try:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/auth/login":
                body = self.read_body(); result = login(str(body.get("username", "")).strip(), str(body.get("password", "")))
                if not result: self.send_json(401, {"ok": False, "error": "用户名或密码错误"}); return
                token, user = result; self.send_response(200); self.send_header("Set-Cookie", f"workbench_session={token}; HttpOnly; SameSite=Lax; Max-Age=604800; Path=/"); self.send_header("Content-Type", "application/json; charset=utf-8"); data = json.dumps({"ok": True, "user": user}, ensure_ascii=False).encode(); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            if path == "/api/auth/register":
                body = self.read_body(); username = str(body.get("username", "")).strip(); password = str(body.get("password", "")); display_name = str(body.get("display_name") or username).strip()
                if not username or len(username) < 3 or len(username) > 64: raise ValueError("用户名长度必须为 3-64 位")
                if len(password) < 6: raise ValueError("密码至少需要 6 位")
                db = __import__("core.storage", fromlist=["connect"]).connect()
                try:
                    db.execute("INSERT INTO users(username,password_hash,display_name,is_admin,enabled) VALUES(?,?,?,0,1)", (username, _hash_password(password), display_name or username)); db.commit()
                except Exception as exc:
                    db.rollback()
                    if "UNIQUE" in str(exc).upper(): raise ValueError("用户名已存在")
                    raise
                finally: db.close()
                self.send_json(201, {"ok": True, "message": "注册成功，请等待管理员开通功能权限"}); return
            if path == "/api/auth/logout": logout(self._token()); self.send_response(200); self.send_header("Set-Cookie", "workbench_session=; Max-Age=0; Path=/"); self.send_header("Content-Type", "application/json; charset=utf-8"); data=b'{"ok":true}'; self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            user = self._auth(path)
            if user is False: return
            if (path == "/api/jenkins/register" or path.startswith("/api/jenkins/permissions/")) and not user["is_admin"]:
                self.send_json(403, {"ok": False, "error": "仅管理员可管理 Jenkins 用户"}); return
            if path.startswith("/api/scheduler") or path.startswith("/api/schedules") or path.startswith("/api/scheduler-tasks") or path.startswith("/api/code-review"):
                if not role_at_least(user, "advanced"):
                    self.send_json(403, {"ok": False, "code": "forbidden", "error": "需要高级用户及以上权限"}); return
            if path.startswith("/api/central-") or path.startswith("/api/central-server") or path.startswith("/api/openai-agent") or path.startswith("/api/server-maintenance"):
                if not role_at_least(user, "developer"):
                    self.send_json(403, {"ok": False, "code": "forbidden", "error": "需要开发者及以上权限"}); return
            if path == "/api/users":
                body = self.read_body(); username = str(body.get("username", "")).strip(); password = str(body.get("password", "")); role = str(body.get("role", "user"))
                if not username or len(password) < 6: raise ValueError("用户名和密码（至少6位）不能为空")
                if role not in ROLES: raise ValueError("用户角色无效")
                from core.storage import connect
                with connect() as db:
                    cur = db.execute("INSERT INTO users(username,password_hash,display_name,is_admin,role) VALUES(?,?,?,?,?)", (username, _hash_password(password), str(body.get("display_name") or username), int(role == "admin"), role))
                self.send_json(201, {"ok": True, "id": cur.lastrowid}); return
            if path.startswith("/api/users/"):
                from core.storage import connect
                uid = int(path.split("/")[3]); body = self.read_body()
                db = connect()
                try:
                    db.execute("BEGIN IMMEDIATE")
                    target = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
                    if not target: raise ValueError("用户不存在")
                    if path.endswith("/reset-password"):
                        password = body.get("password", "")
                        if not isinstance(password, str) or len(password) < 6: raise ValueError("密码至少6位")
                        db.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_password(password), uid))
                        db.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
                    else:
                        role = body.get("role", target["role"]); enabled = body.get("enabled", bool(target["enabled"]))
                        if role not in ROLES or type(enabled) is not bool: raise ValueError("角色或状态无效")
                        if uid == user["id"] and (role != "admin" or not enabled): raise ValueError("不能降级或停用当前管理员")
                        if target["role"] == "admin" and (role != "admin" or not enabled):
                            if db.execute("SELECT count(*) FROM users WHERE role='admin' AND enabled=1 AND id!=?", (uid,)).fetchone()[0] == 0: raise ValueError("必须保留一个启用的管理员")
                        db.execute("UPDATE users SET role=?,is_admin=?,enabled=?,display_name=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (role, int(role == "admin"), int(enabled), body.get("display_name", target["display_name"]), uid))
                        db.execute("DELETE FROM user_permissions WHERE user_id=?", (uid,))
                    db.commit()
                except Exception:
                    db.rollback(); raise
                finally: db.close()
                self.send_json(200, {"ok": True}); return
            result = view_router.dispatch(ViewContext(self, path, self.read_body(), "POST", self._legacy_post))
            if result is not None:
                return result
            return self._legacy_post()
        except (ValueError, KeyError) as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})
        except RuntimeError as exc:
            self.send_json(409, {"ok": False, "error": str(exc)})
        except Exception:
            traceback.print_exc()
            self.send_json(500, {"ok": False, "error": "接口执行失败，请查看服务日志"})

    def _legacy_post(self):
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
            if path == "/api/settings/storage" or path.startswith("/api/settings/storage/"):
                self.send_json(409, {"ok": False, "code": "client_local_only", "error": "Client storage requires the local agent"}); return
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
            repository = ScheduleRepository()
            if path == "/api/scheduler-tasks/create":
                controller = SchedulerController()
                sid = controller.create(str(body["scheduler_type"]), str(body.get("name") or "新任务"), body.get("param", {}), int(body.get("run_type", 1)), str(body.get("run_time", "04:00")))
                self.send_json(201, {"ok": True, "id": sid}); return
            if path == "/api/scheduler-tasks/delete":
                deleted = SchedulerController().delete(str(body["id"]))
                self.send_json(200, {"ok": deleted}); return
            if path == "/api/scheduler-tasks/code-review/run":
                self.send_json(200, {"ok": True, "task": start_task(str(body.get("project_path", "")), str(body.get("branch", "")), body.get("skill_paths", ["skills"]), bool(body.get("allow_extra_rules", False)), str(body.get("failure_threshold", "high")), str(body.get("schedule_id") or CodeReviewScheduler.schedule_id))}); return
            if path == "/api/scheduler-tasks/code-review/stop":
                self.send_json(200, {"ok": True, "task": stop_task()}); return
            if path == "/api/scheduler-tasks/code-review/config":
                self.send_json(200, {"ok": True, "task": update_task_config(str(body.get("project_path", "")), str(body.get("branch", "")), body.get("skill_paths", ["skills"]), bool(body.get("allow_extra_rules", False)), str(body.get("failure_threshold", "high")), str(body.get("schedule_id") or CodeReviewScheduler.schedule_id))}); return
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
                entry = str(Path(__file__).resolve().parent.parent / "tools" / "code-review-agent" / "run_task.py")
                schedule_id = str(body.get("schedule_id", "code-review-daily"))
                args = {"project_path": project_path, "branch": body.get("branch", "main"), "skill_paths": body.get("skill_paths", ["skills"]), "config_path": body.get("config_path")}
                # 工具和计划必须在同一事务中更新，避免半配置状态。
                repository.sync_code_review(
                    (tool_id, "Unity 代码检查 Agent", "local_process", entry, str(Path(entry).parent)),
                    (schedule_id, body.get("name", "Unity 代码每日检查"), tool_id, "daily", body.get("time", "04:00"), json.dumps(args, ensure_ascii=False), int(body.get("timeout", 900)), 0, 1, time.time(), "scheduled", "scheduler", 5),
                )
                self.send_json(201, {"ok": True, "tool_id": tool_id, "schedule_id": schedule_id, "schedule_type": "daily", "schedule_expr": body.get("time", "04:00")}); return
            if path == "/api/scheduler-tasks/code-review":
                self.send_json(200, {"ok": True, "task": task_payload()}); return
            if path.startswith("/api/scheduler-tasks/code-review/"):
                sid = urllib.parse.unquote(path.rsplit("/", 1)[-1])
                row = repository.get_schedule(sid)
                if not row: self.send_json(404, {"ok": False, "error": "task not found"}); return
                self.send_json(200, {"ok": True, "task": task_payload(sid)}); return
            self.send_json(404, {"ok": False, "error": "not found"})
        except Exception as exc:
            self.send_json(400, {"ok": False, "error": repr(exc)})

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/login", "/register"):
            if current(self._token()):
                self.send_response(302); self.send_header("Location", "/"); self.end_headers(); return
            kind = path[1:]; data = standalone_auth_html(kind).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
        if path == "/api/auth/session":
            user = current(self._token()); self.send_json(200, {"ok": True, "user": user, "modules": MODULES}); return
        if path == "/api/modules": self.send_json(200, {"ok": True, "modules": MODULES}); return
        if path == "/api/users":
            user = current(self._token())
            if not user or not user["is_admin"]: self.send_json(403, {"ok": False, "error": "仅管理员可管理用户"}); return
            db = __import__("core.storage", fromlist=["connect"]).connect(); rows = db.execute("SELECT id,username,display_name,is_admin,enabled,role FROM users ORDER BY id").fetchall(); result=[]
            for row in rows: result.append({"id":row["id"],"username":row["username"],"display_name":row["display_name"],"is_admin":bool(row["is_admin"]),"enabled":bool(row["enabled"]),"role":row["role"]})
            db.close(); self.send_json(200, {"ok": True, "users": result}); return
        user = self._auth(path)
        if user is False: return
        result = view_router.dispatch(ViewContext(self, path, {}, "GET", self._legacy_get))
        if result is not None:
            return result
        return self._legacy_get()

    def _legacy_get(self):
        """返回静态页面或只读接口数据。"""
        try:
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                if not current(self._token()):
                    self.send_response(302); self.send_header("Location", "/login"); self.end_headers(); return
                data = index_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
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
                self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data); return
            if path == "/api/scheduler-tasks":
                self.send_json(200, {"ok": True, "tasks": [task_payload()]}); return
            if path == "/api/scheduler-tasks/code-review":
                self.send_json(200, {"ok": True, "task": task_payload()}); return
            if path.startswith("/api/scheduler-tasks/code-review/"):
                sid = urllib.parse.unquote(path.rsplit("/", 1)[-1])
                self.send_json(200, {"ok": True, "task": task_payload(sid)}); return
            if path == "/api/health":
                self.send_json(200, {"ok": True, "service": "machine-dashboard-server", "mode": "local"})
                return
            if path == "/api/processes":
                self.send_json(200, {"processes": PROCESS_MANAGER.snapshot()}); return
            if path == "/api/settings/storage" or path.startswith("/api/settings/storage/"):
                self.send_json(409, {"ok": False, "code": "client_local_only", "error": "Client storage requires the local agent"}); return
            self.send_json(404, {"ok": False, "error": "not found"})
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": repr(exc), "trace": traceback.format_exc()[-2000:]})


def main():
    # 启动时先读取本地日志配置，再创建运行日志和调试日志。
    settings = load_local_settings()
    ensure_admin()
    logger = AppLogger("machine-dashboard")
    logger.info("服务启动 host=%s port=%s log_level=%s debug_log=%s output_dir=%s", HOST, PORT, settings["log_level"], settings["debug_log"], settings["output_dir"])
    logger.debug("调试日志已开启")
    OPERATION_LOG.info("[feature=machine-dashboard] server.started url=http://%s:%s host_scope=%s", HOST, PORT, "lan" if HOST in {"0.0.0.0", "::"} else "local")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        OPERATION_LOG.info("[feature=machine-dashboard] server.stopped")

