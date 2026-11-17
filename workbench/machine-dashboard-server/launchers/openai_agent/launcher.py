from __future__ import annotations
import os, socket, subprocess, sys, json, urllib.request
from pathlib import Path
from process_manager.contracts import ManagedProcess, ProcessHandle
from process_manager.operation_log import get_operation_logger

class OpenAIAgentLauncher(ManagedProcess):
    name = "openai-agent"
    def __init__(self, project_root: Path, port: int = 8765) -> None:
        self.project_root, self.port, self.logger = project_root, port, get_operation_logger()
        self._log_handle = None
        self._process: subprocess.Popen | None = None
    def start(self) -> ProcessHandle:
        root = self.project_root.resolve()
        self.logger.info("launcher.openai_agent.start.begin root=%s port=%s", root, self.port)
        if not (root / "codex_agent" / "openai_gateway.py").is_file():
            self.logger.error("launcher.openai_agent.gateway_missing path=%s", root / "codex_agent" / "openai_gateway.py")
            raise FileNotFoundError(f"OpenAiAgent gateway not found: {root}")
        from core.settings import get_settings
        output_root = get_settings().output_dir
        log_path = output_root / "openai-agent" / "gateway-launcher.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = log_path.open("a", encoding="utf-8", buffering=1)
        kwargs = {"cwd": str(root), "env": {**os.environ, "CODEX_GATEWAY_PORT": str(self.port), "PYTHONPATH": str(root)}, "stdout": self._log_handle, "stderr": subprocess.STDOUT}
        if os.name == "nt":
            # Keep the gateway visible like the central-server launcher.
            # This makes its interpreter errors and startup banner observable
            # when the Agent is started from the dashboard.
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE
        # Run the gateway module directly.  The process manager owns this
        # child process and can terminate the whole process tree on stop.
        # Prefer the agent's local environment so dependencies such as httpx
        # are independent of whichever Python started the dashboard server.
        python_exe = root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        interpreter = str(python_exe) if python_exe.is_file() else sys.executable
        command = [interpreter, "-m", "codex_agent.openai_gateway"]
        self.logger.info("launcher.openai_agent.exec interpreter=%s cwd=%s command=%s log=%s", interpreter, root, command, log_path)
        try:
            proc = subprocess.Popen(command, **kwargs)
            self._process = proc
        except Exception:
            self.logger.exception("launcher.openai_agent.start.error command=%s", command)
            self._log_handle.close()
            self._log_handle = None
            raise
        self.logger.info(
            "launcher.openai_agent.start pid=%s port=%s root=%s interpreter=%s cwd=%s command=%s child_log=%s",
            proc.pid,
            self.port,
            root,
            interpreter,
            root,
            command,
            log_path,
        )
        return ProcessHandle(proc.pid, self.port)
    def stop(self, handle: ProcessHandle | None = None) -> None:
        pid = handle.pid if handle else None
        proc = self._process
        if pid and proc and proc.pid == pid:
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
            self._process = None
        if pid and proc and proc.pid == pid and self._log_handle:
            self._log_handle.close()
            self._log_handle = None
        self.logger.info("launcher.openai_agent.stop.end pid=%s", pid)
    def is_running(self, handle: ProcessHandle | None = None) -> bool:
        if not handle or not handle.pid:
            return False
        proc = self._process
        if not proc or proc.pid != handle.pid or proc.poll() is not None:
            return False
        # The owned child is authoritative during startup; the gateway exposes
        # /health for external readiness checks without claiming other PIDs.
        return True

    def chat(self, message: str, model: str | None = None) -> str:
        root = self.project_root.resolve()
        python_exe = root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
        interpreter = str(python_exe) if python_exe.is_file() else sys.executable
        command = [interpreter, str(Path(__file__).with_name("chat.py")), message, "--project-root", str(root), "--model", model or os.getenv("CODEX_MODEL", "gpt-5.6-terra")]
        self.logger.info("launcher.openai_agent.chat command=%s", command)
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=120, env={**os.environ, "PYTHONPATH": str(root)})
        if result.returncode:
            self.logger.error("launcher.openai_agent.chat.error code=%s stderr=%s", result.returncode, result.stderr.strip())
            raise RuntimeError(result.stderr.strip() or "Agent 对话失败")
        return result.stdout.strip()
