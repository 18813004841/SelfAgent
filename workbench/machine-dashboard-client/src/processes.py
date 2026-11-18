from __future__ import annotations
import os, socket, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
from .paths import ClientPaths

@dataclass
class Handle:
    pid: int
    port: int = 0

class LocalProcesses:
    def __init__(self, paths: ClientPaths) -> None:
        self.paths = paths
        self._client = None
        self._codex = None
        self._codex_log = None

    def client_status(self, agent) -> dict:
        client = agent.storage() / "central-client"
        version_file = client / "VERSION"
        version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else ""
        running = self._client is not None and self._client.poll() is None
        return {
            "service": "central-client",
            "scope": "client-local",
            "running": running,
            "pid": self._client.pid if running else None,
            "storage_dir": str(agent.storage()),
            "client_dir": str(client),
            "client_dir_exists": client.is_dir(),
            "client_entry_exists": (client / "control_worker" / "client.py").is_file(),
            "version": version,
            "central_server_url": agent.settings.get("central_server_url", ""),
            "machine_id": agent.settings.get("machine_id") or socket.gethostname(),
        }

    def start_client(self, agent) -> Handle:
        if self._client and self._client.poll() is None:
            return Handle(self._client.pid)
        client = agent.storage() / "central-client"
        entry = client / "control_worker" / "client.py"
        if not entry.is_file():
            raise ValueError("本机尚未安装中央服务器客户端，请先下载并安装")
        server = str(agent.settings.get("central_server_url") or "").strip()
        if not server:
            raise ValueError("请填写本机可访问的中央服务器地址")
        token = str(agent.settings.get("central_token") or os.environ.get("MACHINE_CONTROL_TOKEN") or "dev-token")
        machine = str(agent.settings.get("machine_id") or socket.gethostname())
        command = [sys.executable, "-m", "control_worker.client", "--server", server, "--machine-id", machine, "--token", token, "--capability", "shell", "--capability", "unity", "--capability", "adb"]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        self._client = subprocess.Popen(command, cwd=client, env={**os.environ, "PYTHONPATH": str(client)}, creationflags=flags)
        return Handle(self._client.pid)

    def stop_client(self) -> None:
        self._stop(self._client)
        self._client = None

    def codex_status(self) -> dict:
        running = self._codex is not None and self._codex.poll() is None
        return {"running": running, "pid": self._codex.pid if running else None, "port": 4500, "console": running, "scope": "client-local"}

    def start_codex(self) -> Handle:
        if self._codex and self._codex.poll() is None:
            return Handle(self._codex.pid, 4500)
        script = Path(__file__).resolve().parents[1] / "scripts" / "start_local_codex.bat"
        if not script.is_file():
            raise FileNotFoundError("本机 Codex 启动脚本不存在")
        log = self.paths.root / "logs" / "local-codex.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        handle = log.open("a", encoding="utf-8", buffering=1)
        self._codex_log = handle
        flags = subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        env = {**os.environ, "CODEX_APP_SERVER_PORT": "4500"}
        env.setdefault("HOME", os.environ.get("USERPROFILE", str(Path.home())))
        env.setdefault("CODEX_HOME", str(self.paths.root / "codex-runtime"))
        Path(env["CODEX_HOME"]).mkdir(parents=True, exist_ok=True)
        self._codex = subprocess.Popen(["cmd.exe", "/d", "/c", str(script)], cwd=script.parent, env=env, creationflags=flags, stdout=handle, stderr=subprocess.STDOUT)
        return Handle(self._codex.pid, 4500)

    def stop_codex(self) -> None:
        self._stop(self._codex)
        self._codex = None
        if self._codex_log:
            self._codex_log.close()
            self._codex_log = None

    @staticmethod
    def _stop(proc) -> None:
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
