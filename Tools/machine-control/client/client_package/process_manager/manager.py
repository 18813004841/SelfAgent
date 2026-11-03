from __future__ import annotations

import os
import subprocess
from pathlib import Path


class LocalProcessManager:
    """Manage the worker process using only local files and OS APIs."""

    def __init__(self, root: Path, python: str = "python") -> None:
        self.root = root
        self.python = python
        self.pid_file = root / "data" / "central-client.pid"

    def start(self, server: str, machine_id: str, token: str) -> int:
        self.root.mkdir(parents=True, exist_ok=True)
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        command = [self.python, "-m", "control_worker.client", "--server", server, "--machine-id", machine_id, "--token", token]
        proc = subprocess.Popen(command, cwd=self.root, env={**os.environ, "PYTHONPATH": str(self.root)})
        self.pid_file.write_text(str(proc.pid), encoding="utf-8")
        return proc.pid

    def stop(self) -> None:
        if not self.pid_file.exists():
            return
        pid = int(self.pid_file.read_text(encoding="utf-8"))
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(pid, 15)
        self.pid_file.unlink(missing_ok=True)

    def status(self) -> dict:
        pid = int(self.pid_file.read_text(encoding="utf-8")) if self.pid_file.exists() else None
        running = False
        if pid:
            try:
                if os.name == "nt":
                    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
                    running = f'"{pid}"' in out
                else:
                    os.kill(pid, 0)
                    running = True
            except Exception:
                running = False
        if not running:
            self.pid_file.unlink(missing_ok=True)
        return {"running": running, "pid": pid}
