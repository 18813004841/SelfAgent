"""View 层双通道日志。

view 日志记录接口生命周期；debug 日志记录对应业务模块的调试细节。
两者使用独立目录和文件，可在同一次请求中同时写入。
"""
from __future__ import annotations
from pathlib import Path
from core.Log import AppLogger

ROOT = Path(__file__).resolve().parent
VIEW_LOG = ROOT / "logs"
FEATURE_LOG_ROOT = ROOT.parent

class ViewLogger:
    def __init__(self, feature: str, debug_dir: Path | str, debug_only: bool = False):
        self.feature = feature
        self.debug_only = debug_only
        from core.settings import get_settings
        options = {"debug": True} if debug_only else {}
        self.view = AppLogger(f"view.{feature}", get_settings().view_log_path, **options)
        self.debug_log = AppLogger(f"debug.{feature}", debug_dir, **options)

    def debug(self, message, *args):
        self.view.debug(message, *args)
        self.debug_log.debug(message, *args)

    def info(self, message, *args):
        (self.view.debug if self.debug_only else self.view.info)(message, *args)
        self.debug_log.debug(message, *args)

    def warning(self, message, *args):
        if self.debug_only:
            return self.debug(message, *args)
        self.view.warning(message, *args)
        self.debug_log.warning(message, *args)

    def request(self, method, path, body=None):
        if self.debug_only:
            return self.debug("request method=%s path=%s", method, path)
        self.view.info("request method=%s path=%s", method, path)
        self.debug_log.debug("request method=%s path=%s body=%r", method, path, body or {})

    def response(self, status):
        if self.debug_only:
            return self.debug("response status=%s", status)
        self.view.info("response status=%s", status)
        self.debug_log.debug("response status=%s", status)

    def error(self, message, *args):
        if self.debug_only:
            return self.debug(message, *args)
        self.view.error(message, *args)
        self.debug_log.error(message, *args)

from functools import lru_cache

@lru_cache(maxsize=None)
def get_logger(feature: str, debug_dir: Path | str | None = None, debug_only: bool = False) -> ViewLogger:
    return ViewLogger(feature, debug_dir or (FEATURE_LOG_ROOT / feature / "logs"), debug_only)



