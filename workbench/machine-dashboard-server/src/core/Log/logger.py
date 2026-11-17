"""工作台通用日志。

运行日志始终写入文件；调试日志只有打开调试模式后才写入。
"""
from __future__ import annotations

import logging
import os
import re
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from core.settings import LogLevel

_HANDLERS: dict[str, RotatingFileHandler] = {}
_SENSITIVE = re.compile(r"(?i)(bearer\s+|(?:token|password|passwd|secret|api[_-]?key)\s*[=:]\s*)([^\s,;]+)")

def _redact(value):
    if isinstance(value, str):
        return _SENSITIVE.sub(lambda m: m.group(1) + "[REDACTED]", value)
    return value

class RedactingFormatter(logging.Formatter):
    """Redact the rendered record, including arguments and exception text."""

    def format(self, record):
        return _redact(super().format(record))


class AppLogger:
    """同时提供分级运行日志和可开关的调试日志。"""

    def __init__(self, name: str, log_dir: Path | str | None = None, debug: bool | None = None):
        from core.settings import get_settings
        settings = get_settings()
        # 调用方未指定时，使用本地配置里的日志等级和调试开关。
        self._debug_override = debug
        self.debug_enabled = settings.debug_log if debug is None else debug
        level = getattr(logging, settings.log_level, logging.INFO)
        base_log_dir = settings.log_path
        if log_dir is None:
            log_dir = base_log_dir
        else:
            requested = Path(log_dir)
            log_dir = requested if requested.is_absolute() else base_log_dir / requested
        log_dir = Path(log_dir)
        self.log_dir = log_dir
        self.log_file = self.initialize_log_file()
        formatter = RedactingFormatter("%(asctime)s %(levelname)s %(message)s")

        # 运行日志持续记录正常流程、警告和错误。
        logger_key = f"{name}.{self.log_file}"
        self.runtime = logging.getLogger(f"{logger_key}.runtime")
        self.runtime.setLevel(level)
        self.runtime.propagate = False
        handler_key = str(self.log_file.resolve()).lower()
        shared_handler = _HANDLERS.get(handler_key)
        if shared_handler is None:
            shared_handler = RotatingFileHandler(self.log_file, maxBytes=10 * 1024 * 1024,
                                                  backupCount=7, encoding="utf-8")
            shared_handler.setFormatter(formatter)
            _HANDLERS[handler_key] = shared_handler
        if not self.runtime.handlers:
            self.runtime.addHandler(shared_handler)

        # 调试日志单独存放，避免平时刷满运行日志。
        self.debugger = logging.getLogger(f"{logger_key}.debug")
        self.debugger.setLevel(logging.DEBUG)
        self.debugger.propagate = False
        if not self.debugger.handlers:
            self.debugger.addHandler(shared_handler)

    def initialize_log_file(self) -> Path:
        """同一启动会话在同一目录共用日志文件，已存在时追加。"""
        timestamp = os.environ.get("LOCAL_WORKBENCH_START_TIMESTAMP")
        if not timestamp:
            raise RuntimeError(
                "日志启动时间戳未初始化，请先由工作台 server.py 设置 "
                "LOCAL_WORKBENCH_START_TIMESTAMP"
            )
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._prune_old_logs()
        return self.log_dir / f"{timestamp}.log"

    def _prune_old_logs(self) -> None:
        """Remove old session logs; retention is opt-in and bounded to this directory."""
        raw = os.environ.get("WORKBENCH_LOG_RETENTION_DAYS", "30")
        try:
            days = int(raw)
        except ValueError:
            raise ValueError("WORKBENCH_LOG_RETENTION_DAYS 必须是非负整数")
        if days < 0:
            raise ValueError("WORKBENCH_LOG_RETENTION_DAYS 必须是非负整数")
        cutoff = time.time() - days * 86400
        current = os.environ.get("LOCAL_WORKBENCH_START_TIMESTAMP", "")
        for path in self.log_dir.glob("*.log"):
            try:
                stem = path.name[:-4]
                if not re.fullmatch(r"\d{8}_\d{6}_\d{6}", stem) or stem == current or path.is_symlink():
                    continue
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                continue

    def set_debug(self, enabled: bool) -> None:
        """打开或关闭调试日志。"""
        self.debug_enabled = enabled
        self._debug_override = enabled

    def _enabled(self, level: int, *, debug: bool = False) -> bool:
        """每次输出前读取最新日志等级和调试开关。"""
        from core.settings import get_settings
        settings = get_settings()
        minimum = getattr(logging, settings.log_level, logging.INFO)
        self.runtime.setLevel(minimum)
        self.debug_enabled = settings.debug_log if self._debug_override is None else self._debug_override
        is_debug = debug or level == logging.DEBUG
        return level >= minimum and (not is_debug or self.debug_enabled)

    def log(self, level: LogLevel | int | str, message: str, *args) -> None:
        """按调用方传入的级别记录日志，并与配置级别比较。"""
        if isinstance(level, str):
            level = getattr(LogLevel, level.upper(), None)
        elif isinstance(level, LogLevel):
            level = int(level)
        if not isinstance(level, int):
            raise ValueError("日志级别必须是 logging 常量或 DEBUG/INFO/WARNING/ERROR 字符串")
        is_debug = level == logging.DEBUG
        if not self._enabled(level):
            return
        target = self.debugger if is_debug else self.runtime
        target.log(level, message, *args)

    def debug(self, message: str, *args) -> None:
        self.log(logging.DEBUG, message, *args)

    def info(self, message: str, *args) -> None:
        self.log(logging.INFO, message, *args)

    def warning(self, message: str, *args) -> None:
        self.log(logging.WARNING, message, *args)

    def error(self, message: str, *args) -> None:
        self.log(logging.ERROR, message, *args)

    def exception(self, message: str, *args) -> None:
        if self._enabled(logging.ERROR):
            self.runtime.exception(message, *args)
