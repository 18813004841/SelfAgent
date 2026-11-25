"""Central-server assistant orchestration.

The page sends natural-language messages here. This adapter selects a small,
explicit tool set and calls the machine-control HTTP contract; it never exposes
the central token to the browser.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.request
from functools import wraps
from typing import Any

from . import router
from .logging import get_logger

logger = get_logger("central_ai", "central-server")
_active_sessions: set[str] = set()
_active_sessions_lock = threading.Lock()


def _guard_session(fn):
    @wraps(fn)
    def guarded(ctx):
        session_id = str(ctx.body.get("session_id") or "").strip()
        owned = set()
        with _active_sessions_lock:
            if session_id and session_id in _active_sessions:
                raise RuntimeError("该会话的上一条消息仍在执行，请等待完成后再发送")
            if session_id:
                _active_sessions.add(session_id)
                owned.add(session_id)
        ctx.central_ai_owned_sessions = owned
        try:
            return fn(ctx)
        finally:
            with _active_sessions_lock:
                _active_sessions.difference_update(owned)
    return guarded


def _request(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    import sys
    server = sys.modules.get("server") or sys.modules["__main__"]
    port = server.CENTER_PORT
    token = os.environ.get("MACHINE_CONTROL_TOKEN", "dev-token")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def _intent(message: str) -> tuple[str, dict[str, Any]]:
    text = message.strip()
    if re.search(r"健康|可用|连通|服务状态", text):
        return "health", {}
    if re.search(r"连接|链接|在线|客户端|机器列表|有哪些机器", text):
        keyword = next(iter(re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]+", text)), "")
        return "connections", {"keyword": keyword}
    if re.search(r"磁盘|空间", text):
        keyword = next(iter(re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]+", text)), "")
        return "submit_shell", {"keyword": keyword, "command": "df -h"}
    if re.search(r"主机名|hostname", text, re.I):
        keyword = next(iter(re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]+", text)), "")
        return "submit_shell", {"keyword": keyword, "command": "hostname"}
    return "analysis", {}


def _worker_matches(worker: dict[str, Any], keyword: str) -> bool:
    values = [worker.get("machine_id", ""), worker.get("hostname", "")]
    values.extend((worker.get("meta") or {}).get("local_ips", []) or [])
    return any(keyword in str(value) for value in values)


def _choose_worker(keyword: str, workers: list[dict[str, Any]]) -> dict[str, Any] | None:
    online = [w for w in workers if w.get("status") == "online"]
    if keyword:
        matched = [w for w in online if _worker_matches(w, keyword)]
        if len(matched) == 1:
            return matched[0]
        if len(matched) > 1:
            raise ValueError("目标机器不唯一，请提供完整 machine_id 或主机名")
        raise ValueError(f"未找到在线机器：{keyword}")
    if len(online) == 1:
        return online[0]
    raise ValueError("请先指定目标机器")


def _get_workers() -> list[dict[str, Any]]:
    """Return workers with liveness derived from the heartbeat timestamp.

    The control center persists the last registration status, which can remain
    ``online`` after a worker stops.  Keep the assistant on the same liveness
    contract as ``/api/central-server/connections`` instead of exposing that
    stale field directly.
    """
    import sys
    server = sys.modules.get("server") or sys.modules["__main__"]
    from core.central_connections import get_connections

    result = get_connections(server.CENTER_PORT, getattr(server, "MACHINE_CONTROL_SERVER_URL", None))
    if not result.get("available"):
        raise RuntimeError("中央服务器不可用，暂时无法查询机器在线状态")
    return result.get("workers", [])


@router.route("POST", "/api/central-ai/chat", "/api/central-ai/chat-stream")
@_guard_session
def handle(ctx):
    message = str(ctx.body.get("message", "")).strip()
    if not message:
        raise ValueError("message 不能为空")
    logger.info("central_ai.request.begin message_length=%s", len(message))
    import sys
    from pathlib import Path
    from integrations.codex_cli import CodexCliClient, CodexCliError
    server = sys.modules.get("server") or sys.modules["__main__"]
    control_root = Path(__file__).resolve().parents[4] / "Tools" / "machine-control"
    mcp_root = control_root / "server"
    mcp_shared = control_root / "shared"
    mcp_python = control_root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    mcp_python_path = str(mcp_python) if mcp_python.is_file() else sys.executable
    center_url = getattr(server, "MACHINE_CONTROL_SERVER_URL", f"http://127.0.0.1:{server.CENTER_PORT}")
    token = os.environ.get("MACHINE_CONTROL_TOKEN", "dev-token")
    context = ctx.body.get("context") if isinstance(ctx.body.get("context"), dict) else {}
    prompt = ("你是机器管理助手。通过已连接的 machine_control MCP 服务处理用户请求。\n"
              "每次新请求的第一次 MCP 交互必须先读取 machine_control 提供的工具列表/工具说明，确认当前会话实际可用的工具；在完成工具发现前，禁止直接调用 health、list_workers 或任何业务操作。\n"
              "工具发现完成后，再根据用户请求选择需要的工具；需要机器状态时调用 health/list_workers，并且只能操作明确匹配且在线的客户端。\n"
              "每次工具调用前说明发给中央服务器的参数，拿到结果后说明中央服务器返回内容。\n"
              "完成后给用户结论，不要臆造状态，不要绕过 MCP。不要使用 exec_command、文件系统或其他工具；只使用 machine_control MCP。\n\n用户消息：%s\n\n最近客户端上下文（仅供参考，以 MCP 为准）：%s" %
              (message, json.dumps(context, ensure_ascii=False)))
    def toml_string(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)
    mcp_args = ["-m", "control_mcp.server", "--server", center_url, "--token", token]
    config = {
        "mcp_servers.machine_control.default_tools_approval_mode": toml_string("approve"),
        "mcp_servers.machine_control.command": toml_string(mcp_python_path),
        "mcp_servers.machine_control.args": "[" + ", ".join(toml_string(item) for item in mcp_args) + "]",
        "mcp_servers.machine_control.env.PYTHONPATH": toml_string(str(mcp_root) + os.pathsep + str(mcp_shared)),
    }
    logger.info("central_ai.mcp.config mode=toml_fields command=%s server=%s", mcp_python_path, center_url)
    requested_model = str(ctx.body.get("model") or os.getenv("CODEX_MODEL", "gpt-5.6-sol"))
    models = list(dict.fromkeys([requested_model, "gpt-5.6-terra", "gpt-5.5"]))
    streaming = ctx.path.endswith("/chat-stream")
    disconnected = False
    started_session = None
    if streaming:
        ctx.request.send_response(200)
        ctx.request.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        ctx.request.send_header("Cache-Control", "no-store, no-transform")
        ctx.request.send_header("Connection", "close")
        ctx.request.end_headers()
        ctx.request.close_connection = True

    def emit(payload):
        nonlocal disconnected
        if not streaming or disconnected:
            return
        try:
            ctx.request.wfile.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            ctx.request.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            disconnected = True

    def on_event(event):
        nonlocal started_session
        if event.get("type") == "thread.started":
            started_session = event.get("thread_id")
            if started_session:
                with _active_sessions_lock:
                    _active_sessions.add(started_session)
                    ctx.central_ai_owned_sessions.add(started_session)
        emit({"type": "event", "event": event})

    result = None
    last_error = None
    for model in models:
        try:
            logger.info("central_ai.codex.begin model=%s", model)
            result = CodexCliClient(model=model, timeout=900).execute(
                prompt, cwd=control_root, session_id=str(ctx.body.get("session_id") or "") or None,
                config_overrides=config, ignore_user_config=True,
                on_event=on_event if streaming else None, cancel=lambda: disconnected)
            break
        except CodexCliError as exc:
            last_error = exc
            if "already has an active writer" in str(exc).lower():
                message = "该 Codex 会话正在被其他进程使用，请等待原任务结束后重试。"
                if streaming:
                    emit({"type": "error", "error": message})
                    return True
                raise RuntimeError(message) from exc
            if "capacity" not in str(exc).lower() or started_session:
                if streaming:
                    emit({"type": "error", "error": str(exc)})
                    return True
                raise
            logger.warning("central_ai.codex.capacity model=%s", model)
        except Exception as exc:
            if not streaming:
                raise
            logger.exception("central_ai.codex.failed")
            emit({"type": "error", "error": str(exc)})
            return True
    if result is None:
        if streaming:
            emit({"type": "error", "error": str(last_error or "模型暂时不可用")})
            return True
        raise last_error or RuntimeError("模型暂时不可用")
    session_id = next((event.get("thread_id") for event in result.events
                       if event.get("type") == "thread.started" and event.get("thread_id")), None)
    if not session_id:
        if streaming:
            emit({"type": "error", "error": "Codex 未返回会话 ID，无法保存对话上下文"})
            return True
        raise RuntimeError("Codex 未返回会话 ID，无法保存对话上下文")
    logger.info("central_ai.request.end events=%s reply_length=%s", len(result.events), len(result.text))
    if streaming:
        emit({"type": "complete", "reply": result.text, "session_id": session_id})
    else:
        ctx.request.send_json(200, {"ok": True, "mode": "codex-mcp", "reply": result.text,
                                    "session_id": session_id, "events": result.events})
    return True
    tool, args = _intent(message)
    logger.info("central_ai.tool.select tool=%s", tool)
    if tool == "analysis":
        ctx.request.send_json(200, {"ok": True, "mode": "analysis", "tool": None,
                                    "reply": "这个请求需要进一步分析。请明确目标机器和要检查的内容，例如：检查 build-mac-01 的磁盘空间。"})
        return True
    if tool == "health":
        result = _request("/health")
        ctx.request.send_json(200, {"ok": True, "mode": "tool", "tool": "health", "result": result,
                                    "reply": "中央服务器连接正常。"})
        return True
    workers = _get_workers()
    if tool == "connections":
        keyword = args["keyword"]
        selected = [w for w in workers if not keyword or _worker_matches(w, keyword)]
        online = sum(w.get("status") == "online" for w in selected)
        ctx.request.send_json(200, {"ok": True, "mode": "tool", "tool": "list_workers", "result": {"workers": selected},
                                    "reply": f"已查询中央服务器：匹配 {len(selected)} 台客户端，在线 {online} 台。"})
        return True
    worker = _choose_worker(args["keyword"], workers)
    task = _request("/api/tasks", "POST", {"machine_id": worker["machine_id"], "kind": "shell",
        "payload": {"command": args["command"], "timeout": 30}}).get("task", {})
    ctx.request.send_json(202, {"ok": True, "mode": "tool", "tool": "submit_shell_task",
                                "worker": worker, "task": task,
                                "reply": f"已向 {worker.get('hostname') or worker['machine_id']} 提交检查任务。"})
    return True
