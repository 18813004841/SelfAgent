"""Browser-local companion for the remote workbench. Binds to loopback only."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import tempfile
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from .codex_tasks import CodexTaskStore
from .paths import ClientPaths
from .processes import LocalProcesses

DEFAULT_PORT = 18991
CLIENT_VERSION = (Path(__file__).resolve().parents[1] / "VERSION").read_text(encoding="utf-8").strip()
LOG_MAX_BYTES = int(os.environ.get("WORKBENCH_LOCAL_AGENT_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUPS = int(os.environ.get("WORKBENCH_LOCAL_AGENT_LOG_BACKUPS", "3"))
if LOG_MAX_BYTES < 1 or not 1 <= LOG_BACKUPS <= 100:
    raise ValueError("日志大小必须为正数，历史文件数必须在 1 到 100 之间")


class LocalAgent:
    def __init__(self, paths: ClientPaths, dashboard_url: str) -> None:
        self.paths = paths
        self.dashboard_url = dashboard_url.rstrip("/")
        self.tasks = CodexTaskStore(paths.data / "codex-tasks.sqlite")
        self.processes = LocalProcesses(paths)
        self._lock = threading.Lock()
        self.settings = self._load()

    def _load(self) -> dict:
        if self.paths.config.is_file():
            # Windows PowerShell 5 may write UTF-8 with a BOM.  The fixed
            # per-user config must remain readable regardless of the writer.
            value = json.loads(self.paths.config.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("客户机 settings.json 必须是 JSON 对象")
            changed = False
            if not value.get("dashboard_url"):
                value["dashboard_url"] = self.dashboard_url
                changed = True
            if not value.get("storage_dir"):
                value["storage_dir"] = str(self.paths.root / "client" / "storage")
                changed = True
            if changed:
                self.settings = value
                self.save()
            return value
        defaults = {"storage_dir": str(self.paths.root / "client" / "storage"), "dashboard_url": self.dashboard_url, "local_codex_url": "ws://127.0.0.1:4500", "central_server_url": "", "central_token": "", "machine_id": socket.gethostname()}
        self.settings = defaults
        self.save()
        return defaults

    def save(self) -> None:
        self.paths.config.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.paths.config.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.paths.config)

    def storage(self) -> Path:
        value = Path(self.settings.get("storage_dir") or self.paths.root / "client" / "storage").expanduser()
        value.mkdir(parents=True, exist_ok=True)
        return value

    def choose_directory(self) -> str | None:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(initialdir=str(self.storage()))
        root.destroy()
        return selected or None

    def install_client(self, payload: bytes) -> Path:
        target = self.storage() / "central-client"
        if self.processes.client_status(self)["running"]:
            raise ValueError("请先停止本机中央客户端再安装")
        archive_path = self.paths.root / "cache" / "central-client.zip"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(payload)
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                relative = Path(entry.filename.replace("\\", "/"))
                if relative.is_absolute() or ".." in relative.parts or ":" in entry.filename:
                    raise ValueError("安装包包含非法路径")
                if entry.external_attr >> 16 & 0o170000 == 0o120000:
                    raise ValueError("安装包不允许符号链接")
            if sum(entry.file_size for entry in archive.infolist()) > 128 * 1024 * 1024:
                raise ValueError("安装包解压体积过大")
            staging = Path(tempfile.mkdtemp(prefix="central-client-", dir=self.storage()))
            try:
                archive.extractall(staging)
                source = staging / "central-client" if (staging / "central-client").is_dir() else staging
                if not (source / "control_worker" / "client.py").is_file():
                    raise ValueError("安装包缺少客户端入口")
                version = self._package_version(source)
                if target.exists():
                    backup = target.with_name("central-client.previous")
                    if backup.exists():
                        shutil.rmtree(backup)
                    target.rename(backup)
                try:
                    shutil.move(str(source), str(target))
                except Exception:
                    if backup.exists() and not target.exists():
                        backup.rename(target)
                    raise
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        return target

    @staticmethod
    def _package_version(source: Path) -> str:
        version_file = source / "VERSION"
        if not version_file.is_file():
            raise ValueError("安装包缺少 VERSION")
        version = version_file.read_text(encoding="utf-8").strip()
        if not version:
            raise ValueError("安装包 VERSION 为空")
        return version

    def download_client(self) -> Path:
        package_url = os.environ.get("CENTRAL_CLIENT_PACKAGE_URL") or f"{self.dashboard_url}/api/central-client/download"
        with urlopen(Request(package_url), timeout=30) as response:
            payload = response.read()
        return self.install_client(payload)


def make_handler(agent: LocalAgent):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            with agent._lock:
                self._write_log(fmt, *args)

        def _write_log(self, fmt: str, *args) -> None:
            agent.paths.log.parent.mkdir(parents=True, exist_ok=True)
            if agent.paths.log.exists() and agent.paths.log.stat().st_size >= LOG_MAX_BYTES:
                for index in range(LOG_BACKUPS, 0, -1):
                    source = agent.paths.log.with_suffix(agent.paths.log.suffix + f".{index}")
                    target = agent.paths.log.with_suffix(agent.paths.log.suffix + f".{index + 1}")
                    if source.exists():
                        if index == LOG_BACKUPS:
                            source.unlink()
                        else:
                            source.replace(target)
                agent.paths.log.replace(agent.paths.log.with_suffix(agent.paths.log.suffix + ".1"))
            with agent.paths.log.open("a", encoding="utf-8") as handle:
                handle.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _send(self, status: int, payload: dict | bytes, content_type="application/json") -> None:
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            origin = self.headers.get("Origin")
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            if not self._trusted_request():
                self._send(403, {"ok": False, "error": "untrusted dashboard origin"})
                return
            self.send_response(204)
            origin = self.headers.get("Origin")
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                # Chromium sends this header when a LAN page reaches a
                # loopback service (Private Network Access preflight).
                if self.headers.get("Access-Control-Request-Private-Network") == "true":
                    self.send_header("Access-Control-Allow-Private-Network", "true")
                self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:
            self._route("GET")

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            self._route("POST", raw)

        def _trusted_request(self) -> bool:
            host = urlparse("http://" + self.headers.get("Host", "")).hostname
            origin = self.headers.get("Origin")
            if host not in {"127.0.0.1", "localhost", "::1"}:
                return False
            if origin is None or origin.rstrip("/") == agent.dashboard_url.rstrip("/"):
                return True
            # The same server is commonly opened as either its LAN address or
            # a loopback address.  A client-local agent may safely accept the
            # loopback aliases for the configured dashboard port; it never
            # accepts an arbitrary remote origin.
            configured = urlparse(agent.dashboard_url)
            requested = urlparse(origin)
            return (
                requested.scheme == configured.scheme
                and requested.hostname in {"127.0.0.1", "localhost", "::1"}
                and requested.port == configured.port
            )

        def _json_body(self, raw: bytes) -> dict:
            if not raw:
                return {}
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            return value

        def _route(self, method: str, raw: bytes = b"") -> None:
            if not self._trusted_request():
                # Keep the loopback agent closed to arbitrary web pages, but
                # return enough non-sensitive context to diagnose a changed
                # LAN address without inspecting the client config manually.
                self._send(403, {
                    "ok": False,
                    "error": "untrusted dashboard origin",
                    "configured_dashboard_url": agent.dashboard_url,
                    "request_origin": self.headers.get("Origin", ""),
                    "hint": "请用当前浏览器地址重新运行 setup-client.ps1 后重启本机服务",
                })
                return
            path = urlparse(self.path).path
            try:
                if path == "/health" and method == "GET":
                    self._send(200, {"ok": True, "service": "workbench-local-agent", "version": CLIENT_VERSION, "dashboard_url": agent.dashboard_url})
                    return
                if path == "/api/local-agent/version" and method == "GET":
                    self._send(200, {"ok": True, "service": "workbench-local-agent", "version": CLIENT_VERSION, "scope": "client-local"})
                elif path == "/api/settings/storage" and method == "GET":
                    self._send(200, {"ok": True, "settings": {"storage_dir": str(agent.storage()), "config_path": str(agent.paths.config)}, "scope": "client-local"})
                elif path == "/api/settings/storage" and method == "POST":
                    body = self._json_body(raw)
                    value = str(body.get("storage_dir", "")).strip()
                    if not value:
                        raise ValueError("storage_dir is required")
                    resolved = Path(value).expanduser().resolve()
                    resolved.mkdir(parents=True, exist_ok=True)
                    agent.settings["storage_dir"] = str(resolved)
                    agent.save()
                    self._send(200, {"ok": True, "settings": {"storage_dir": str(resolved)}, "scope": "client-local"})
                elif path == "/api/settings/storage/choose" and method == "POST":
                    selected = agent.choose_directory()
                    if selected:
                        agent.settings["storage_dir"] = str(Path(selected).resolve())
                        agent.save()
                    self._send(200, {"ok": True, "selected": bool(selected), "settings": {"storage_dir": agent.settings["storage_dir"]}})
                elif path == "/api/settings/storage/reset" and method == "POST":
                    default = agent.paths.root / "client" / "storage"
                    default.mkdir(parents=True, exist_ok=True)
                    agent.settings["storage_dir"] = str(default)
                    agent.save()
                    self._send(200, {"ok": True, "settings": {"storage_dir": str(default)}, "scope": "client-local"})
                elif path == "/api/settings/storage/open" and method in {"GET", "POST"}:
                    target = agent.storage()
                    if os.name == "nt":
                        os.startfile(target)  # noqa: S606 - explicit local user action
                    else:
                        subprocess.Popen(["xdg-open", str(target)])
                    self._send(200, {"ok": True, "storage_dir": str(target)})
                elif path == "/api/central-client/status" and method == "GET":
                    self._send(200, {"ok": True, **agent.processes.client_status(agent)})
                elif path == "/api/central-client/install" and method == "POST":
                    target = agent.download_client() if not raw else agent.install_client(raw)
                    self._send(200, {"ok": True, "client_dir": str(target)})
                elif path == "/api/central-client/start" and method == "POST":
                    body = self._json_body(raw)
                    for key in ("central_server_url", "central_token", "machine_id"):
                        if body.get(key):
                            agent.settings[key] = str(body[key])
                    agent.save()
                    handle = agent.processes.start_client(agent)
                    self._send(200, {"ok": True, "pid": handle.pid})
                elif path == "/api/central-client/stop" and method == "POST":
                    agent.processes.stop_client()
                    self._send(200, {"ok": True, "running": False})
                elif path.startswith("/api/local-codex/"):
                    self._codex(path, method, raw)
                else:
                    self._send(404, {"ok": False, "error": "not found"})
            except ValueError as exc:
                self._send(400, {"ok": False, "error": str(exc)})
            except Exception as exc:
                self._send(500, {"ok": False, "error": str(exc)})

        def _codex(self, path: str, method: str, raw: bytes) -> None:
            if path == "/api/local-codex/choose" and method == "POST":
                selected = agent.choose_directory()
                self._send(200, {"ok": True, "selected": bool(selected), "project_path": selected or ""})
            elif path == "/api/local-codex/config" and method == "GET":
                self._send(200, {"ok": True, "config": {"local_codex_url": agent.settings.get("local_codex_url", "ws://127.0.0.1:4500")}, "scope": "client-local"})
            elif path == "/api/local-codex/config" and method == "POST":
                body = self._json_body(raw)
                url = str(body.get("local_codex_url", "")).strip()
                parsed = urlparse(url)
                if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
                    raise ValueError("地址必须是 ws:// 或 wss://")
                if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                    raise ValueError("本地 Codex 地址必须指向本机")
                agent.settings["local_codex_url"] = url
                agent.save()
                self._send(200, {"ok": True, "config": {"local_codex_url": url}})
            elif path == "/api/local-codex/test" and method == "POST":
                address = agent.settings.get("local_codex_url", "ws://127.0.0.1:4500")
                probe = address.replace("ws://", "http://", 1).replace("wss://", "https://", 1).rstrip("/") + "/readyz"
                try:
                    with urlopen(Request(probe), timeout=3) as response:
                        reachable = 200 <= response.status < 300
                    self._send(200, {"ok": True, "reachable": reachable, "address": address, "message": "连接成功" if reachable else "服务未就绪"})
                except Exception as exc:
                    self._send(200, {"ok": True, "reachable": False, "address": address, "message": f"无法连接：{exc}"})
            elif path == "/api/local-codex/status" and method == "GET":
                self._send(200, {"ok": True, **agent.processes.codex_status()})
            elif path == "/api/local-codex/start" and method == "POST":
                handle = agent.processes.start_codex()
                self._send(200, {"ok": True, "running": True, "pid": handle.pid, "port": handle.port})
            elif path == "/api/local-codex/stop" and method == "POST":
                agent.processes.stop_codex()
                self._send(200, {"ok": True, "running": False})
            elif path == "/api/local-codex/tasks" and method == "GET":
                self._send(200, {"ok": True, "tasks": agent.tasks.list()})
            elif path == "/api/local-codex/tasks" and method == "POST":
                body = self._json_body(raw)
                action = body.get("action")
                if action == "delete":
                    agent.tasks.delete(str(body.get("id", "")))
                    self._send(200, {"ok": True})
                elif action == "update":
                    agent.tasks.update(body)
                    self._send(200, {"ok": True})
                else:
                    name = str(body.get("name", "")).strip()
                    cwd = str(body.get("cwd", "")).strip()
                    if not name or not cwd:
                        raise ValueError("任务名称和工程工作区不能为空")
                    if not Path(cwd).expanduser().is_dir():
                        raise ValueError("工程工作区不存在或不是目录")
                    self._send(201, {"ok": True, "task": agent.tasks.create(name, cwd)})
            elif path == "/api/local-codex/task" and method == "POST":
                body = self._json_body(raw)
                prompt = str(body.get("prompt", "")).strip()
                record_id = str(body.get("id", "")).strip()
                if not prompt or not record_id:
                    raise ValueError("任务 ID 和内容不能为空")
                task = agent.tasks.get(record_id)
                if not task:
                    raise ValueError("任务不存在")
                cwd = str(body.get("cwd") or task["cwd"])
                if not Path(cwd).expanduser().is_dir():
                    raise ValueError("工程工作区不存在或不是目录")
                timeout = body.get("timeout_seconds")
                submitted = agent.tasks.submit(prompt, cwd, record_id, task.get("session_id"), timeout)
                self._send(202, {"ok": True, **submitted})
            elif path == "/api/local-codex/task/cancel" and method == "POST":
                body = self._json_body(raw)
                self._send(200, {"ok": True, **agent.tasks.cancel(str(body.get("id", "")))})
            elif path == "/api/local-codex/task" and method == "GET":
                task_id = parse_qs(urlparse(self.path).query).get("task_id", [""])[0]
                task = agent.tasks.running(task_id)
                if not task:
                    self._send(404, {"ok": False, "error": "任务不存在"})
                else:
                    if task["status"] != "running":
                        agent.tasks.save_result(task)
                    visible = {key: value for key, value in task.items() if key != "process"}
                    self._send(200, {"ok": True, "task": visible})
            else:
                self._send(404, {"ok": False, "error": "not found"})

    return Handler


def serve(paths: ClientPaths, host: str, port: int, dashboard_url: str) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("local agent must bind to loopback")
    class ExclusiveLocalServer(ThreadingHTTPServer):
        # HTTPServer enables SO_REUSEADDR, which permits competing listeners
        # on Windows. A second Agent must fail instead of serving unpredictably.
        allow_reuse_address = False

        def server_bind(self):
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    agent = LocalAgent(paths, dashboard_url)
    try:
        server = ExclusiveLocalServer((host, port), make_handler(agent))
    except OSError as exc:
        raise SystemExit(f"Local Agent cannot bind {host}:{port}; stop the existing agent before restarting: {exc}") from exc
    paths.pid.parent.mkdir(parents=True, exist_ok=True)
    paths.pid.write_text(str(os.getpid()), encoding="utf-8")
    try:
        server.serve_forever()
    finally:
        agent.processes.stop_client()
        agent.processes.stop_codex()
        server.server_close()
        if paths.pid.is_file():
            paths.pid.unlink()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("WORKBENCH_LOCAL_AGENT_PORT", DEFAULT_PORT)))
    parser.add_argument("--dashboard-url", default=os.environ.get("WORKBENCH_DASHBOARD_URL", ""))
    parser.add_argument("--data-dir", default=os.environ.get("WORKBENCH_CLIENT_DATA_DIR", ""))
    args = parser.parse_args()
    root = Path(args.data_dir) if args.data_dir else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LocalWorkbench"
    dashboard_url = args.dashboard_url
    if not dashboard_url:
        config = ClientPaths(root).config
        if config.is_file():
            try:
                dashboard_url = str(json.loads(config.read_text(encoding="utf-8-sig")).get("dashboard_url", ""))
            except (OSError, ValueError):
                dashboard_url = ""
    serve(ClientPaths(root), args.host, args.port, dashboard_url or "http://127.0.0.1:18888")


if __name__ == "__main__":
    main()


