from pathlib import Path
from . import router
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'src/core/logs'
logger = get_logger('settings', DEBUG_LOG_DIR)

@router.route("GET", "/api/settings/storage", "/api/settings/storage/open")
@router.route("POST", "/api/settings/storage", "/api/settings/storage/reset", "/api/settings/storage/choose")
def handle(ctx):
    logger.debug("handling %s %s", ctx.method, ctx.path)
    """保存目录的读取、写入、重置和打开。"""
    import sys
    server = sys.modules.get("server") or sys.modules["__main__"]
    get_settings, default_settings, save_settings = server.get_settings, server.default_settings, server.save_settings
    import os, platform, subprocess
    from pathlib import Path
    if ctx.path == "/api/settings/storage" and ctx.method == "GET":
        ctx.request.send_json(200, {"ok": True, "settings": get_settings(), "default": default_settings()["storage_dir"]})
    elif ctx.path == "/api/settings/storage" and ctx.method == "POST":
        value = str(ctx.body.get("storage_dir", "")).strip()
        if not value: raise ValueError("storage_dir is required")
        save_settings({"storage_dir": str(Path(value).expanduser().resolve())})
        ctx.request.send_json(200, {"ok": True, "settings": get_settings()})
    elif ctx.path == "/api/settings/storage/reset":
        save_settings(default_settings()); ctx.request.send_json(200, {"ok": True, "settings": get_settings()})
    elif ctx.path == "/api/settings/storage/open":
        target = Path(get_settings().get("storage_dir", default_settings()["storage_dir"])); target.mkdir(parents=True, exist_ok=True)
        if os.name == "nt": os.startfile(str(target))
        elif platform.system() == "Darwin": subprocess.Popen(["open", str(target)])
        else: subprocess.Popen(["xdg-open", str(target)])
        ctx.request.send_json(200, {"ok": True, "storage_dir": str(target)})
    else:
        return ctx.legacy()
    return True





