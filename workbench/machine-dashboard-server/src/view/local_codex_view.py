"""本地 Codex App Server 配置与连通性接口。"""
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from local_codex.tasks import tasks
from core.repositories import LocalCodexTaskRepository
import json, uuid
from . import router
from .logging import get_logger

logger = get_logger("local_codex", Path(__file__).resolve().parents[2] / "src/core/logs")
DEFAULT_URL = "ws://127.0.0.1:4500"
TASK_REPOSITORY = LocalCodexTaskRepository()

def _settings(server):
    value = server.get_settings()
    return {"local_codex_url": value.get("local_codex_url", DEFAULT_URL)}


@router.route("GET", "/api/local-codex/config", "/api/local-codex/test", "/api/local-codex/status", "/api/local-codex/task", "/api/local-codex/tasks")
@router.route("POST", "/api/local-codex/config", "/api/local-codex/test", "/api/local-codex/start", "/api/local-codex/stop", "/api/local-codex/task", "/api/local-codex/tasks")
def handle(ctx):
    ctx.request.send_json(409, {"ok": False, "error": "本地 Codex 由浏览这台电脑的本地接入服务管理", "code": "client_local_only"})
    return True
    import sys
    server = sys.modules.get("server") or sys.modules["__main__"]
    if ctx.path == "/api/local-codex/tasks" and ctx.method == "GET":
        rows = TASK_REPOSITORY.list()
        ctx.request.send_json(200, {"ok": True, "tasks": [dict(row) | {"messages": json.loads(row["messages_json"]), "skill_paths": json.loads(row["skill_paths_json"] or "[]")} for row in rows]})
    elif ctx.path == "/api/local-codex/tasks" and ctx.method == "POST":
        if ctx.body.get("action") == "delete":
            TASK_REPOSITORY.delete(str(ctx.body.get("id", "")))
            ctx.request.send_json(200, {"ok": True}); return True
        if ctx.body.get("action") == "update":
            existing = TASK_REPOSITORY.get_fields(str(ctx.body.get("id", "")))
            if not existing: raise ValueError("任务不存在")
            if "skill_paths" not in ctx.body:
                ctx.body["skill_paths"] = json.loads(existing["skill_paths_json"] or "[]")
            if "allow_extra_rules" not in ctx.body:
                ctx.body["allow_extra_rules"] = bool(existing["allow_extra_rules"])
            messages = json.dumps(ctx.body.get("messages") or [], ensure_ascii=False); skills = json.dumps(ctx.body.get("skill_paths") or [], ensure_ascii=False)
            TASK_REPOSITORY.update(str(ctx.body.get("id", "")), cwd=str(ctx.body.get("cwd", "")), status=str(ctx.body.get("status", "idle")), prompt=str(ctx.body.get("prompt", "")), messages=ctx.body.get("messages") or [], log=str(ctx.body.get("log", "")), skill_paths=ctx.body.get("skill_paths") or [], allow_extra_rules=ctx.body.get("allow_extra_rules"))
            ctx.request.send_json(200, {"ok": True}); return True
        name = str(ctx.body.get("name", "")).strip(); cwd = str(ctx.body.get("cwd", "")).strip()
        if not name or not cwd: raise ValueError("任务名称和工程工作区不能为空")
        task_id = uuid.uuid4().hex; TASK_REPOSITORY.create(task_id, name, cwd)
        ctx.request.send_json(201, {"ok": True, "task": {"id": task_id, "name": name, "cwd": cwd, "status": "idle", "messages": []}})
    elif ctx.path == "/api/local-codex/task" and ctx.method == "POST":
        prompt = str(ctx.body.get("prompt", "")).strip()
        if not prompt: raise ValueError("任务内容不能为空")
        cwd = str(ctx.body.get("cwd") or Path(server.get_settings().get("storage_dir", Path.cwd())).resolve())
        if not Path(cwd).expanduser().is_dir():
            raise ValueError("工程工作区不存在或不是目录")
        record_id = str(ctx.body.get("id", "")).strip()
        if not record_id: raise ValueError("任务 ID 不能为空")
        row = TASK_REPOSITORY.get_fields(record_id, "messages_json, session_id")
        if not row: raise ValueError("任务不存在")
        messages = json.loads(row["messages_json"] or "[]")
        messages.append({"role": "user", "content": prompt})
        TASK_REPOSITORY.mark_running(record_id, cwd, prompt, messages)
        result = tasks.submit(prompt, cwd, record_id, row["session_id"])
        ctx.request.send_json(202, {"ok": True, **result})
    elif ctx.path == "/api/local-codex/task" and ctx.method == "GET":
        task_id = ""
        from urllib.parse import parse_qs, urlparse
        task_id = parse_qs(urlparse(ctx.request.path).query).get("task_id", [""])[0]
        task = tasks.get(task_id)
        if not task: ctx.request.send_json(404, {"ok": False, "error": "任务不存在"})
        else:
            if task["status"] != "running":
                row = TASK_REPOSITORY.get_fields(task_id, "messages_json")
                messages = json.loads(row["messages_json"] or "[]") if row else []
                output = "\n\n".join(event.get("text") or event.get("message") or json.dumps(event, ensure_ascii=False) for event in task["events"])
                if not messages or messages[-1].get("role") != "assistant": messages.append({"role": "assistant", "content": output or "（无输出）"})
                else: messages[-1]["content"] = output or "（无输出）"
                session_id = next((event.get("thread_id") for event in task["events"] if event.get("thread_id")), task.get("session_id"))
                TASK_REPOSITORY.save_result(task_id, task["status"], session_id, messages, output)
            ctx.request.send_json(200, {"ok": True, "task": task})
    elif ctx.path == "/api/local-codex/status":
        item = server.PROCESS_MANAGER.snapshot().get("local-codex", {})
        launcher = server.PROCESS_MANAGER._entry("local-codex").process
        server_pid = launcher.listener_pid()
        ctx.request.send_json(200, {"ok": True, "running": item.get("status") == "running", "pid": item.get("pid"), "server_pid": server_pid, "port": item.get("port"), "console": item.get("status") == "running", "ready": bool(server_pid)})
    elif ctx.path == "/api/local-codex/start":
        handle = server.PROCESS_MANAGER.start("local-codex")
        ctx.request.send_json(200, {"ok": True, "running": True, "pid": handle.pid, "port": handle.port})
    elif ctx.path == "/api/local-codex/stop":
        server.PROCESS_MANAGER.stop("local-codex"); ctx.request.send_json(200, {"ok": True, "running": False})
    elif ctx.path == "/api/local-codex/config" and ctx.method == "GET":
        ctx.request.send_json(200, {"ok": True, "config": _settings(server), "default": DEFAULT_URL})
    elif ctx.path == "/api/local-codex/config":
        raw = str(ctx.body.get("local_codex_url", "")).strip()
        parsed = urlparse(raw)
        if parsed.scheme not in {"ws", "wss", "unix"} or not parsed.netloc and parsed.scheme != "unix":
            raise ValueError("地址必须是 ws://、wss:// 或 unix:// 格式")
        current = server.get_settings()
        current["local_codex_url"] = raw
        server.save_settings(current)
        ctx.request.send_json(200, {"ok": True, "config": _settings(server)})
    elif ctx.path == "/api/local-codex/test":
        config = _settings(server); address = config["local_codex_url"]
        if address.startswith(("ws://", "wss://")):
            probe = address.replace("ws://", "http://", 1).replace("wss://", "https://", 1).rstrip("/") + "/readyz"
            try:
                with urlopen(Request(probe, method="GET"), timeout=3) as response:
                    ok = 200 <= response.status < 300
                ctx.request.send_json(200, {"ok": ok, "reachable": ok, "address": address, "message": "连接成功" if ok else "服务未就绪"})
            except Exception as exc:
                ctx.request.send_json(200, {"ok": True, "reachable": False, "address": address, "message": f"无法连接：{exc}"})
        else:
            ctx.request.send_json(200, {"ok": True, "reachable": False, "address": address, "message": "Unix Socket 地址已保存，请通过 App Server 客户端验证"})
    return True
