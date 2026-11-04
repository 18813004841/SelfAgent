from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
import subprocess
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

    def cleanup(self, handle: ProcessHandle | None = None) -> list[int]:
        """Terminate processes listening on this launcher's managed port."""
        if os.name != "nt":
            return []
        port = handle.port if handle else None
        if not port:
            return []
        output = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
        killed: list[int] = []
        for line in output.splitlines():
            fields = line.split()
            if len(fields) >= 5 and fields[0].upper() == "TCP" and fields[1].endswith(f":{port}") and fields[3].upper() == "LISTENING":
                try:
                    pid = int(fields[4])
                    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    killed.append(pid)
                except ValueError:
                    pass
        return killed
