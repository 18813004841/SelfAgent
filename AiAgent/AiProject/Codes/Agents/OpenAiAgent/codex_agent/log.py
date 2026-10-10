"""OpenAiAgent logging configuration.

This module reuses the shared logging implementation while giving this agent
its own default log directory.  Logs are kept next to the agent project so
running the CLI from another working directory does not change their location.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

try:
    from Log.log import LoggerManager as _LoggerManager
except ModuleNotFoundError:  # Running the project without ``Codes`` on PYTHONPATH.
    _BASE_LOG_PATH = Path(__file__).resolve().parents[3] / "Log" / "log.py"
    _spec = spec_from_file_location("aiagent_base_log", _BASE_LOG_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Unable to load base logger from {_BASE_LOG_PATH}")
    _base_log = module_from_spec(_spec)
    _spec.loader.exec_module(_base_log)
    _LoggerManager = _base_log.LoggerManager


_AGENT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_LOG_DIR = _AGENT_ROOT / "logs"


class OpenAiAgentLoggerManager(_LoggerManager):
    """Logger manager with an ``OpenAiAgent/logs`` default destination."""

    # LoggerManager's singleton storage is inherited, so define a separate
    # slot to avoid sharing configuration with other applications.
    _instance = None

    def configure(self, *, log_dir: str | Path = _DEFAULT_LOG_DIR, **kwargs: object):
        """Configure the shared agent logger, defaulting to the agent folder."""
        return super().configure(log_dir=log_dir, **kwargs)


_manager = OpenAiAgentLoggerManager()


def get_logger():
    """Return the OpenAiAgent logger."""
    return _manager.logger


def configure_logging(**kwargs: object):
    """Configure the OpenAiAgent logger explicitly."""
    return _manager.configure(**kwargs)


logger = get_logger()

__all__ = ["OpenAiAgentLoggerManager", "configure_logging", "get_logger", "logger"]
