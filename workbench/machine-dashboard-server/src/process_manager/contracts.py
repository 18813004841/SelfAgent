from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum


class ProcessStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


@dataclass
class ProcessHandle:
    pid: int | None
    port: int


class ManagedProcess(ABC):
    """Adapter contract for a process that can be started and stopped."""

    name: str

    @abstractmethod
    def start(self) -> ProcessHandle:
        raise NotImplementedError

    @abstractmethod
    def stop(self, handle: ProcessHandle | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_running(self, handle: ProcessHandle | None = None) -> bool:
        raise NotImplementedError
