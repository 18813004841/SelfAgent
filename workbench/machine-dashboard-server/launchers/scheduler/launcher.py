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
        self._process: subprocess.Popen | None = None
        self.logger = get_operation_logger()

    def start(self) -> ProcessHandle:
        self.logger.info("launcher.scheduler.start.begin script=%s", self.script)
        kwargs = {"cwd": str(self.script.parent.parent), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen([sys.executable, str(self.script)], **kwargs)
        self._process = proc
        self.logger.info("launcher.scheduler.start.end pid=%s", proc.pid)
        return ProcessHandle(proc.pid, 0)

    def stop(self, handle: ProcessHandle | None = None) -> None:
        self.logger.info("launcher.scheduler.stop.begin pid=%s", handle.pid if handle else None)
        # 只允许停止当前 ProcessManager 持有的句柄；PID 文件不能证明所有权。
        pid = handle.pid if handle and handle.pid else None
        proc = self._process
        if not pid or proc is None or proc.pid != pid:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        self._process = None
        self.pid_file.unlink(missing_ok=True)
        self.logger.info("launcher.scheduler.stop.end pid=%s", pid)

    def is_running(self, handle: ProcessHandle | None = None) -> bool:
        proc = self._process
        return bool(handle and proc and proc.pid == handle.pid and proc.poll() is None)
