from __future__ import annotations
import os, subprocess, socket, re
from pathlib import Path
from process_manager.contracts import ManagedProcess, ProcessHandle
from process_manager.operation_log import get_operation_logger

class LocalCodexLauncher(ManagedProcess):
    name = "local-codex"
    def __init__(self, project_root: Path, port: int = 4500):
        self.project_root, self.port = project_root.resolve(), port
        self.logger = get_operation_logger(); self._log_handle = None
        self._process: subprocess.Popen | None = None
    def start(self) -> ProcessHandle:
        listener = self.listener_pid()
        if listener:
            raise RuntimeError(f"Codex 端口 {self.port} 已被其他进程占用，拒绝接管未知进程 {listener}")
        script = self.project_root / "src" / "local_codex" / "start_local_codex.bat"
        if not script.is_file(): raise FileNotFoundError(f"Codex 启动脚本不存在: {script}")
        from core.settings import get_settings, get_user_root
        log = get_settings().output_dir / "local-codex" / "launcher.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = log.open("a", encoding="utf-8", buffering=1)
        # 一键启动需要可视化进程窗口，沿用其他托管进程的独立控制台模式。
        flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        env = {**os.environ, "CODEX_APP_SERVER_PORT": str(self.port)}
        env.setdefault("HOME", os.environ.get("USERPROFILE", str(Path.home())))
        env.setdefault("CODEX_HOME", str(get_user_root() / "codex-runtime"))
        try:
            Path(env["CODEX_HOME"]).mkdir(parents=True, exist_ok=True)
            proc = subprocess.Popen(["cmd.exe", "/d", "/c", str(script)], cwd=self.project_root, env=env, creationflags=flags, close_fds=True, stdout=self._log_handle, stderr=subprocess.STDOUT)
        except Exception:
            self._log_handle.close()
            self._log_handle = None
            self.logger.exception("launcher.local_codex.start.failed")
            raise
        self._process = proc
        self.logger.info("launcher.local_codex.start pid=%s port=%s", proc.pid, self.port)
        return ProcessHandle(proc.pid, self.port)
    def stop(self, handle=None):
        proc = self._process
        if handle and handle.pid and proc and proc.pid == handle.pid:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
            self._process = None
            if self._log_handle: self._log_handle.close(); self._log_handle = None
    def is_running(self, handle=None):
        proc = self._process
        return bool(handle and proc and proc.pid == handle.pid and proc.poll() is None)

    def listener_pid(self):
        try:
            out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout
        except Exception:
            return None
        for line in out.splitlines():
            if f"127.0.0.1:{self.port}" in line and "LISTENING" in line:
                match = re.search(r"(\d+)\s*$", line)
                return int(match.group(1)) if match else None
        return None
