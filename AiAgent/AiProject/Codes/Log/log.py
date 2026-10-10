"""Application logging utilities.

Use :func:`get_logger` at call sites so the application shares one configured
logger and does not add duplicate handlers when modules are imported repeatedly.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Optional

_DEFAULT_LOGGER_NAME = "aiagent"
_DEFAULT_LOG_DIR = Path("logs")
_DEFAULT_LOG_FILE = "app.log"
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024
_DEFAULT_BACKUP_COUNT = 5
_DEFAULT_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | "
    "%(filename)s:%(lineno)d | %(message)s"
)


class LoggerManager:
    """Thread-safe singleton that owns the application's logger configuration."""

    _instance: Optional["LoggerManager"] = None
    _instance_lock = Lock()

    def __new__(cls) -> "LoggerManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._config_lock = Lock()
        self._logger = logging.getLogger(_DEFAULT_LOGGER_NAME)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        self._configured = False

    @property
    def logger(self) -> logging.Logger:
        """Return the shared logger, configuring defaults on first use."""
        if not self._configured:
            self.configure()
        return self._logger

    def configure(
        self,
        *,
        log_dir: str | Path = _DEFAULT_LOG_DIR,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        backup_count: int = _DEFAULT_BACKUP_COUNT,
        level: int | str = logging.INFO,
        console: bool = True,
        filename: str = _DEFAULT_LOG_FILE,
        fmt: str = _DEFAULT_FORMAT,
    ) -> logging.Logger:
        """Configure and return the singleton logger.

        ``max_bytes`` controls rotation size and ``backup_count`` controls the
        number of rotated files retained. Calling this repeatedly safely
        replaces handlers with the new configuration.
        """
        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")
        if backup_count < 0:
            raise ValueError("backup_count must be zero or greater")
        if not filename:
            raise ValueError("filename must not be empty")

        resolved_level = logging._nameToLevel.get(level.upper(), level) if isinstance(level, str) else level
        if not isinstance(resolved_level, int):
            raise ValueError(f"unknown log level: {level!r}")

        with self._config_lock:
            path = Path(log_dir)
            path.mkdir(parents=True, exist_ok=True)
            formatter = logging.Formatter(fmt)

            for handler in self._logger.handlers[:]:
                handler.close()
                self._logger.removeHandler(handler)

            file_handler = RotatingFileHandler(
                path / filename,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

            if console:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                self._logger.addHandler(console_handler)

            self._logger.setLevel(resolved_level)
            self._configured = True
            return self._logger


_manager = LoggerManager()


def get_logger() -> logging.Logger:
    """Return the application's singleton logger."""
    return _manager.logger


def configure_logging(**kwargs: object) -> logging.Logger:
    """Configure the singleton logger; useful during application startup."""
    return _manager.configure(**kwargs)


# Convenient singleton for callers that prefer ``from ...log import logger``.
logger = get_logger()

__all__ = ["LoggerManager", "configure_logging", "get_logger", "logger"]
