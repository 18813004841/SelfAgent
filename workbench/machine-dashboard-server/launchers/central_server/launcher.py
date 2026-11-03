from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

from process_manager.contracts import ManagedProcess, ProcessHandle
from process_manager.operation_log import get_operation_logger


class CentralServerLauncher(ManagedProcess):
    name = "central-server"

    def __init__(self, root: Path, port: int = 18765, pid_file: Path | None = None) -> None:
        self.root, self.port, self.pid_file = root, port, pid_file
        self.logger = get_operation_logger()

    def start(self) -> ProcessHandle:
        self.logger.info("launcher.central_server.start.begin root=%s port=%s", self.root, self.port)
        if os.name == "nt":
            command = ["cmd.exe", "/d", "/k", str(self.root / "server" / "start_center_lan_visible.bat")]
            flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            command, flags = ["open", str(self.root / "server" / "start_center_lan_visible.command")], 0
        proc = subprocess.Popen(command, cwd=self.root, creationflags=flags)
        if self.pid_file:
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
            self.pid_file.write_text(str(proc.pid), encoding="utf-8")
        self.logger.info("launcher.central_server.start.end pid=%s port=%s", proc.pid, self.port)
        return ProcessHandle(proc.pid, self.port)

    def stop(self, handle: ProcessHandle | None = None) -> None:
        self.logger.info("launcher.central_server.stop.begin pid=%s", handle.pid if handle else None)
        if not handle or not handle.pid:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(handle.pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(handle.pid, 15)
        if self.pid_file:
            self.pid_file.unlink(missing_ok=True)
        self.logger.info("launcher.central_server.stop.end pid=%s", handle.pid if handle else None)

    def is_running(self, handle: ProcessHandle | None = None) -> bool:
        if handle and handle.pid:
            try:
                if os.name == "nt":
                    result = subprocess.run(["tasklist", "/FI", f"PID eq {handle.pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True)
                    if f'"{handle.pid}"' not in result.stdout:
                        self.logger.info("launcher.central_server.status pid=%s running=false", handle.pid)
                        return False
                else:
                    os.kill(handle.pid, 0)
            except Exception:
                self.logger.info("launcher.central_server.status pid=%s running=false", handle.pid if handle else None)
                return False
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.35):
                self.logger.info("launcher.central_server.status port=%s running=true", self.port)
                return True
        except OSError:
            self.logger.info("launcher.central_server.status port=%s running=false", self.port)
            return False
