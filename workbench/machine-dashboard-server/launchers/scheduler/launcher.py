from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from process_manager.contracts import ManagedProcess, ProcessHandle
from process_manager.operation_log import get_operation_logger


class SchedulerLauncher(ManagedProcess):
    name = "scheduler"

    def __init__(self, script: Path, pid_file: Path) -> None:
        self.script, self.pid_file = script, pid_file
        self.logger = get_operation_logger()

    def start(self) -> ProcessHandle:
        self.logger.info("launcher.scheduler.start.begin script=%s", self.script)
        kwargs = {"cwd": str(self.script.parent.parent), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen([sys.executable, str(self.script)], **kwargs)
        self.logger.info("launcher.scheduler.start.end pid=%s", proc.pid)
        return ProcessHandle(proc.pid, 0)

    def stop(self, handle: ProcessHandle | None = None) -> None:
        self.logger.info("launcher.scheduler.stop.begin pid=%s", handle.pid if handle else None)
        pid = handle.pid if handle and handle.pid else (int(self.pid_file.read_text()) if self.pid_file.exists() else None)
        if not pid:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(pid, 15)
        self.pid_file.unlink(missing_ok=True)
        self.logger.info("launcher.scheduler.stop.end pid=%s", pid)

    def is_running(self, handle: ProcessHandle | None = None) -> bool:
        try:
            pid = int(self.pid_file.read_text()) if self.pid_file.exists() else (handle.pid if handle else None)
            if not pid:
                return False
            if os.name == "nt":
                out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
                running = f'"{pid}"' in out
                self.logger.info("launcher.scheduler.status pid=%s running=%s", pid, running)
                return running
            os.kill(pid, 0)
            self.logger.info("launcher.scheduler.status pid=%s running=true", pid)
            return True
        except Exception:
            self.logger.info("launcher.scheduler.status pid=%s running=false", locals().get("pid"))
            return False
