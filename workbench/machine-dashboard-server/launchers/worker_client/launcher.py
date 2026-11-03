from __future__ import annotations
import os, socket, shutil, subprocess, sys
from pathlib import Path
from process_manager.contracts import ManagedProcess, ProcessHandle
from process_manager.operation_log import get_operation_logger

class WorkerClientLauncher(ManagedProcess):
    name = "central-client"
    def __init__(self, source_root: Path, local_root_provider, server_url: str = "http://127.0.0.1:18765", token: str = "dev-token", machine_id: str | None = None) -> None:
        self.source_root, self.local_root_provider, self.server_url, self.token = source_root, local_root_provider, server_url, token
        self.machine_id = machine_id or f"win-pack-{socket.gethostname()}"
        self.logger = get_operation_logger()
    def start(self) -> ProcessHandle:
        self.logger.info("launcher.central_client.start.begin server=%s machine=%s", self.server_url, self.machine_id)
        # One downloadable/local package directory for the client runtime.
        local_root = Path(self.local_root_provider()) / "central-client"
        if not (local_root / "control_worker" / "client.py").is_file():
            self.logger.info("launcher.central_client.sync.begin source=%s target=%s", self.source_root, local_root)
            local_root.parent.mkdir(parents=True, exist_ok=True)
            local_root.mkdir(parents=True, exist_ok=True)
            for source, name in ((self.source_root / "client" / "control_worker", "control_worker"), (self.source_root / "shared" / "common", "common"), (self.source_root / "client" / "client_package", "client_package")):
                if source.exists():
                    shutil.copytree(source, local_root / name, dirs_exist_ok=True)
            self.logger.info("launcher.central_client.sync.end target=%s", local_root)
        command = [sys.executable, "-m", "control_worker.client", "--server", self.server_url, "--machine-id", self.machine_id, "--token", self.token, "--capability", "shell", "--capability", "unity", "--capability", "adb"]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | (subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0)
        proc = subprocess.Popen(command, cwd=local_root, env={**os.environ, "PYTHONPATH": str(local_root)}, creationflags=flags)
        self.logger.info("launcher.central_client.start.end pid=%s", proc.pid)
        return ProcessHandle(proc.pid, 0)
    def stop(self, handle: ProcessHandle | None = None) -> None:
        pid = handle.pid if handle else None
        self.logger.info("launcher.central_client.stop.begin pid=%s", pid)
        if not pid: return
        if os.name == "nt": subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else: os.kill(pid, 15)
        self.logger.info("launcher.central_client.stop.end pid=%s", pid)
    def is_running(self, handle: ProcessHandle | None = None) -> bool:
        pid = handle.pid if handle else None
        if not pid: return False
        try:
            if os.name == "nt":
                out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
                running = f'"{pid}"' in out
            else: os.kill(pid, 0); running = True
            self.logger.info("launcher.central_client.status pid=%s running=%s", pid, running)
            return running
        except Exception:
            self.logger.info("launcher.central_client.status pid=%s running=false", pid); return False
