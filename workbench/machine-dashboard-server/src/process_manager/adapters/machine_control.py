from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

from ..contracts import ManagedProcess, ProcessHandle


class MachineControlProcess(ManagedProcess):
    name = "central-server"

    def __init__(self, root: Path, port: int = 18765) -> None:
        self.root = root
        self.port = port

    def start(self) -> ProcessHandle:
        if os.name == "nt":
            command = ["cmd.exe", "/d", "/k", str(self.root / "start_center_lan_visible.bat")]
            flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            command = ["open", str(self.root / "start_center_lan_visible.command")]
            flags = 0
        proc = subprocess.Popen(command, cwd=self.root, creationflags=flags)
        return ProcessHandle(proc.pid, self.port)

    def stop(self, handle: ProcessHandle | None = None) -> None:
        if not handle or not handle.pid:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(handle.pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(handle.pid, 15)

    def is_running(self, handle: ProcessHandle | None = None) -> bool:
        if handle and handle.pid:
            try:
                if os.name == "nt":
                    result = subprocess.run(["tasklist", "/FI", f"PID eq {handle.pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True)
                    if f'"{handle.pid}"' not in result.stdout:
                        return False
                else:
                    os.kill(handle.pid, 0)
            except Exception:
                return False
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.35):
                return True
        except OSError:
            return False
