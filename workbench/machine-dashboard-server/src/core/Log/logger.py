"""工作台通用日志。

运行日志始终写入文件；调试日志只有打开调试模式后才写入。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from core.settings import LogLevel


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
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

        # 运行日志持续记录正常流程、警告和错误。
        logger_key = f"{name}.{self.log_file}"
        self.runtime = logging.getLogger(f"{logger_key}.runtime")
        self.runtime.setLevel(level)
        self.runtime.propagate = False
        if not self.runtime.handlers:
            runtime_handler = logging.FileHandler(self.log_file, encoding="utf-8")
            runtime_handler.setFormatter(formatter)
            self.runtime.addHandler(runtime_handler)

        # 调试日志单独存放，避免平时刷满运行日志。
        self.debugger = logging.getLogger(f"{logger_key}.debug")
        self.debugger.setLevel(logging.DEBUG)
        self.debugger.propagate = False
        if not self.debugger.handlers:
            debug_handler = logging.FileHandler(self.log_file, encoding="utf-8")
            debug_handler.setFormatter(formatter)
            self.debugger.addHandler(debug_handler)

    def initialize_log_file(self) -> Path:
        """同一启动会话在同一目录共用日志文件，已存在时追加。"""
        timestamp = os.environ.get("LOCAL_WORKBENCH_START_TIMESTAMP")
        if not timestamp:
            raise RuntimeError(
                "日志启动时间戳未初始化，请先由工作台 server.py 设置 "
                "LOCAL_WORKBENCH_START_TIMESTAMP"
            )
        self.log_dir.mkdir(parents=True, exist_ok=True)
        return self.log_dir / f"{timestamp}.log"

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
        return level >= minimum and (not debug or self.debug_enabled)

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
