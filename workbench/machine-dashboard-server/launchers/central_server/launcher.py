from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

from process_manager.contracts import ManagedProcess, ProcessHandle
from process_manager.operation_log import get_operation_logger


class CentralServerLauncher(ManagedProcess):
    name = "central-server"

    def __init__(self, root: Path, port: int = 18765, pid_file: Path | None = None, store_path: Path | None = None) -> None:
        self.root, self.port, self.pid_file, self.store_path = root, port, pid_file, store_path
        self._process: subprocess.Popen | None = None
        self.logger = get_operation_logger()

    def start(self) -> ProcessHandle:
        self.logger.info("launcher.central_server.start.begin root=%s port=%s", self.root, self.port)
        python_exe = self.root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        interpreter = str(python_exe) if python_exe.is_file() else os.environ.get("MACHINE_CONTROL_PYTHON", sys.executable)
        store = self.store_path or Path(os.environ.get("MACHINE_CONTROL_STORE", str(self.root / "data" / "control-center.json")))
        store.parent.mkdir(parents=True, exist_ok=True)
        # The central service is consumed by Workers on other machines.  Keep
        # the bind address configurable for isolated deployments, but default
        # to all interfaces so the LAN worker URL is reachable.
        host = os.environ.get("MACHINE_CONTROL_HOST", "0.0.0.0")
        command = [interpreter, "-m", "control_center.server", "--host", host, "--port", str(self.port), "--token", os.environ.get("MACHINE_CONTROL_TOKEN", "dev-token"), "--store", str(store)]
        env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(self.root / "server"), str(self.root / "shared")])}
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        proc = subprocess.Popen(command, cwd=self.root / "server", env=env, creationflags=flags)
        self._process = proc
        if self.pid_file:
            self.pid_file.parent.mkdir(parents=True, exist_ok=True)
            self.pid_file.write_text(str(proc.pid), encoding="utf-8")
        self.logger.info("launcher.central_server.start.end pid=%s port=%s", proc.pid, self.port)
        return ProcessHandle(proc.pid, self.port)

    def stop(self, handle: ProcessHandle | None = None) -> None:
        self.logger.info("launcher.central_server.stop.begin pid=%s", handle.pid if handle else None)
        if not handle or not handle.pid:
            return
        proc = self._process
        if proc is None or proc.pid != handle.pid:
            return
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
        self._process = None
        if self.pid_file:
            self.pid_file.unlink(missing_ok=True)
        self.logger.info("launcher.central_server.stop.end pid=%s", handle.pid if handle else None)

    def is_running(self, handle: ProcessHandle | None = None) -> bool:
        if not handle or not handle.pid:
            return False
        proc = self._process
        if not proc or not handle or proc.pid != handle.pid or proc.poll() is not None:
            return False
        # A live owned launcher is process liveness, not HTTP readiness.
        # Never infer ownership from an occupied port.
        return True
