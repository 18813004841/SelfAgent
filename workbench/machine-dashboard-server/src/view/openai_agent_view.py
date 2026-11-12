from pathlib import Path
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'launchers/openai_agent/logs'
logger = get_logger('openai_agent', DEBUG_LOG_DIR)

@router.route("GET", "/api/openai-agent/status")
@router.route("POST", "/api/openai-agent/start", "/api/openai-agent/stop", "/api/openai-agent/cleanup", "/api/openai-agent/chat")
def handle(ctx):
    logger.debug("handling %s %s", ctx.method, ctx.path)
    """OpenAI Agent 页面：状态、启动、停止、清理和对话。"""
    import sys
    server = sys.modules.get("server") or sys.modules["__main__"]
    PROCESS_MANAGER = server.PROCESS_MANAGER
    import os
    if ctx.path == "/api/openai-agent/status":
        item = PROCESS_MANAGER.snapshot().get("openai-agent", {})
        ctx.request.send_json(200, {"ok": True, "service": "openai-agent", "running": item.get("status") == "running", "pid": item.get("pid"), "port": item.get("port")})
    elif ctx.path == "/api/openai-agent/start":
        handle = PROCESS_MANAGER.start("openai-agent")
        ctx.request.send_json(200, {"ok": True, "pid": handle.pid, "port": handle.port})
    elif ctx.path == "/api/openai-agent/stop":
        PROCESS_MANAGER.stop("openai-agent"); ctx.request.send_json(200, {"ok": True})
    elif ctx.path == "/api/openai-agent/cleanup":
        killed = PROCESS_MANAGER.cleanup("openai-agent")
        ctx.request.send_json(200, {"ok": True, "port": int(os.environ.get("CODEX_GATEWAY_PORT", "8765")), "killed": killed})
    elif ctx.path == "/api/openai-agent/chat":
        message = str(ctx.body.get("message", "")).strip()
        if not message: raise ValueError("message is required")
        answer = PROCESS_MANAGER._entry("openai-agent").process.chat(message, str(ctx.body.get("model") or "gpt-5.6-terra"))
        ctx.request.send_json(200, {"ok": True, "answer": answer})
    return True





