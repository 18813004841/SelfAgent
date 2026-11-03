from __future__ import annotations

from dataclasses import dataclass

from .contracts import ManagedProcess, ProcessHandle, ProcessStatus
from .operation_log import get_operation_logger


@dataclass
class ManagedEntry:
    process: ManagedProcess
    handle: ProcessHandle | None = None
    status: ProcessStatus = ProcessStatus.STOPPED


class ProcessManager:
    """Registry and lifecycle coordinator for managed process adapters."""

    def __init__(self) -> None:
        self._entries: dict[str, ManagedEntry] = {}
        self._logger = get_operation_logger()

    def register(self, process: ManagedProcess) -> None:
        if process.name in self._entries:
            raise ValueError(f"process already registered: {process.name}")
        self._entries[process.name] = ManagedEntry(process)
        self._logger.info("process.register name=%s", process.name)

    def start(self, name: str) -> ProcessHandle:
        entry = self._entry(name)
        if self.status(name) is ProcessStatus.RUNNING:
            return entry.handle  # type: ignore[return-value]
        entry.status = ProcessStatus.STARTING
        self._logger.info("process.start.begin name=%s", name)
        try:
            entry.handle = entry.process.start()
            entry.status = ProcessStatus.RUNNING if entry.process.is_running(entry.handle) else ProcessStatus.FAILED
            self._logger.info("process.start.end name=%s status=%s pid=%s port=%s", name, entry.status.value, entry.handle.pid, entry.handle.port)
            return entry.handle
        except Exception:
            entry.status = ProcessStatus.FAILED
            self._logger.exception("process.start.error name=%s", name)
            raise

    def stop(self, name: str) -> None:
        entry = self._entry(name)
        entry.process.stop(entry.handle)
        self._logger.info("process.stop name=%s pid=%s", name, entry.handle.pid if entry.handle else None)
        entry.status = ProcessStatus.STOPPED
        entry.handle = None

    def status(self, name: str) -> ProcessStatus:
        entry = self._entry(name)
        if entry.handle and entry.process.is_running(entry.handle):
            entry.status = ProcessStatus.RUNNING
        elif entry.status is ProcessStatus.RUNNING:
            entry.status = ProcessStatus.STOPPED
            self._logger.info("process.status.changed name=%s status=stopped", name)
        return entry.status

    def snapshot(self) -> dict[str, dict]:
        return {name: {"status": self.status(name).value, "pid": e.handle.pid if e.handle else None, "port": e.handle.port if e.handle else None} for name, e in self._entries.items()}

    def _entry(self, name: str) -> ManagedEntry:
        if name not in self._entries:
            raise KeyError(f"unknown managed process: {name}")
        return self._entries[name]
