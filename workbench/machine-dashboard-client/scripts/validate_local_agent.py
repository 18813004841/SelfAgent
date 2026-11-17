from __future__ import annotations
import io, json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request, zipfile
from pathlib import Path

def wait_ready(port: int) -> None:
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                assert json.load(response)["ok"] is True
                return
        except Exception:
            time.sleep(0.1)
    raise AssertionError("local agent did not start")

def request(port: int, path: str, data: bytes | None = None, headers: dict | None = None):
    call = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(call, timeout=3) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)

def options(port: int, headers: dict):
    call = urllib.request.Request(f"http://127.0.0.1:{port}/api/settings/storage", headers=headers, method="OPTIONS")
    with urllib.request.urlopen(call, timeout=3) as response:
        return response.status, dict(response.headers)

def zip_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()

def main() -> None:
    port = 18993
    with tempfile.TemporaryDirectory(prefix="wb-client-") as temporary:
        root = Path(temporary)
        client_root = Path(__file__).resolve().parents[1]
        if not (client_root / "src" / "local_agent.py").is_file():
            client_root = Path(__file__).resolve().parents[1] / "workbench" / "machine-dashboard-client"
        env = {**os.environ, "WORKBENCH_LOCAL_AGENT_LOG_MAX_BYTES": "100", "WORKBENCH_LOCAL_AGENT_LOG_BACKUPS": "2", "WORKBENCH_LOCAL_CODEX_ARGV": json.dumps([sys.executable, "-c", "import time; time.sleep(30)"])}
        proc = subprocess.Popen([sys.executable, "-m", "src.local_agent", "--port", str(port), "--dashboard-url", "http://10.0.76.228:18888", "--data-dir", str(root)], cwd=client_root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_ready(port)
            status, preflight = options(port, {"Origin": "http://127.0.0.1:18888", "Access-Control-Request-Method": "POST", "Access-Control-Request-Private-Network": "true"})
            assert status == 204 and preflight.get("Access-Control-Allow-Private-Network") == "true", preflight
            status, loopback = request(port, "/api/settings/storage", headers={"Origin": "http://127.0.0.1:18888"})
            assert status == 200 and loopback["ok"] is True, loopback
            # A server-side address must never gain access unless it is the
            # exact configured browser origin.
            status, denied = request(port, "/api/settings/storage", headers={"Origin": "http://192.168.1.10:18888"})
            assert status == 403, denied
            status, body = request(port, "/api/settings/storage", json.dumps({"storage_dir": str(root / "storage")}).encode(), {"Content-Type": "application/json", "Origin": "http://127.0.0.1:18888"})
            assert status == 200 and body["scope"] == "client-local", body
            config_path = root / "config" / "settings.json"
            assert config_path.is_file(), config_path
            assert Path(json.loads(config_path.read_text(encoding="utf-8"))["storage_dir"]).resolve() == (root / "storage").resolve()
            # Restart the real HTTP process without an explicit origin: both
            # the origin and directory must be restored from this client's file.
            proc.terminate()
            proc.wait(timeout=5)
            proc = subprocess.Popen([sys.executable, "-m", "src.local_agent", "--port", str(port), "--data-dir", str(root)], cwd=client_root, env={**env, "WORKBENCH_DASHBOARD_URL": ""}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            wait_ready(port)
            status, restored = request(port, "/api/settings/storage", headers={"Origin": "http://127.0.0.1:18888"})
            assert status == 200 and Path(restored["settings"]["storage_dir"]).resolve() == (root / "storage").resolve(), restored
            status, body = request(port, "/api/central-client/status", headers={"Origin": "http://evil.example"})
            assert status == 403, body
            good = zip_bytes({"central-client/control_worker/client.py": "print('client')\n"})
            status, body = request(port, "/api/central-client/install", good, {"Content-Type": "application/zip", "Origin": "http://127.0.0.1:18888"})
            assert status == 200 and Path(body["client_dir"], "control_worker", "client.py").is_file(), body
            bad = zip_bytes({"../escape.py": "x"})
            status, body = request(port, "/api/central-client/install", bad, {"Content-Type": "application/zip", "Origin": "http://127.0.0.1:18888"})
            assert status == 400 and not (root.parent / "escape.py").exists(), body
            assert not any(root.rglob("escape.py"))
            for _ in range(12):
                assert request(port, "/health")[0] == 200
            history = list((root / "logs").glob("local-agent.log.*"))
            assert len(history) == 2, history
            assert (root / "logs" / "local-agent.log").is_file()
            headers = {"Content-Type": "application/json", "Origin": "http://127.0.0.1:18888"}
            status, created = request(port, "/api/local-codex/tasks", json.dumps({"name": "timeout", "cwd": str(root)}).encode(), headers)
            assert status == 201, created
            task_id = created["task"]["id"]
            status, submitted = request(port, "/api/local-codex/task", json.dumps({"id": task_id, "prompt": "sleep", "timeout_seconds": 1}).encode(), headers)
            assert status == 202 and submitted["status"] == "running", submitted
            state = {}
            for _ in range(40):
                status, state = request(port, "/api/local-codex/task?task_id=" + task_id)
                if state.get("task", {}).get("status") == "timed_out":
                    break
                time.sleep(0.1)
            assert state.get("task", {}).get("status") == "timed_out", state
            assert isinstance(state["task"].get("returncode"), int), state
            status, duplicate = request(port, "/api/local-codex/tasks", json.dumps({"name": "cancel", "cwd": str(root)}).encode(), headers)
            assert status == 201, duplicate
            cancel_id = duplicate["task"]["id"]
            status, started = request(port, "/api/local-codex/task", json.dumps({"id": cancel_id, "prompt": "sleep", "timeout_seconds": 30}).encode(), headers)
            assert status == 202, started
            status, rejected = request(port, "/api/local-codex/task", json.dumps({"id": cancel_id, "prompt": "again", "timeout_seconds": 30}).encode(), headers)
            assert status == 400 and "正在执行" in rejected["error"], rejected
            status, cancelled = request(port, "/api/local-codex/task/cancel", json.dumps({"id": cancel_id}).encode(), headers)
            assert status == 200, cancelled
            final = {}
            for _ in range(40):
                status, final = request(port, "/api/local-codex/task?task_id=" + cancel_id)
                if final.get("task", {}).get("status") == "cancelled":
                    break
                time.sleep(0.1)
            assert final.get("task", {}).get("status") == "cancelled", final
            status, persisted = request(port, "/api/local-codex/tasks")
            saved = next(item for item in persisted["tasks"] if item["id"] == cancel_id)
            assert saved["status"] == "cancelled", saved
            print("local agent isolated checks passed")
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            with socket.socket() as probe:
                probe.settimeout(0.2)
                assert probe.connect_ex(("127.0.0.1", port)) != 0

if __name__ == "__main__":
    main()
