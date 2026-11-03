"""Unified lifecycle management for locally managed processes."""

from .contracts import ManagedProcess, ProcessHandle, ProcessStatus
from .manager import ProcessManager

__all__ = ["ManagedProcess", "ProcessHandle", "ProcessStatus", "ProcessManager"]
