"""End-to-end center/Worker running-task cancellation on localhost."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "Tools/machine-control/server"
CLIENT = ROOT / "Tools/machine-control/client"
PYTHON = ROOT / "Tools/machine-control/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

def call(url, method="GET", data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", "Bearer e2e-token")
    if data is not None:
        req.data = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())

def main():
    assert PYTHON.is_file(), f"missing project interpreter: {PYTHON}"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="selfagent-running-cancel-") as td:
        store = Path(td) / "center.json"
        env = os.environ.copy(); env["PYTHONPATH"] = os.pathsep.join([str(SERVER), str(ROOT / "Tools/machine-control/shared"), str(CLIENT)])
        center = subprocess.Popen([str(PYTHON), "-m", "control_center.server", "--host", "127.0.0.1", "--port", str(port), "--token", "e2e-token", "--store", str(store)], cwd=SERVER, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        worker = None
        try:
            base = f"http://127.0.0.1:{port}"
            ready = False
            for _ in range(30):
                try:
                    call(base + "/health")
                    ready = True
                    break
                except Exception:
                    time.sleep(.1)
            assert ready, "center did not become ready"
            worker = subprocess.Popen([str(PYTHON), "-m", "control_worker.client", "--server", base, "--machine-id", "e2e-worker", "--token", "e2e-token", "--poll-interval", ".1"], cwd=CLIENT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            registered = False
            for _ in range(30):
                try:
                    if call(base + "/api/workers")["workers"]:
                        registered = True
                        break
                except Exception:
                    pass
                time.sleep(.1)
            assert registered, "worker did not register"
            task = call(base + "/api/tasks", "POST", {"machine_id": "e2e-worker", "kind": "shell", "payload": {"command": "python -c \"import time; time.sleep(30)\"", "timeout": 60}})["task"]
            running = False
            for _ in range(30):
                state = call(base + "/api/tasks/" + task["task_id"])["task"]
                if state["status"] == "running":
                    running = True
                    break
                time.sleep(.1)
            assert running, state
            assert call(base + "/api/tasks/" + task["task_id"] + "/cancel", "POST", {})["task"]["cancel_requested"]
            for _ in range(50):
                state = call(base + "/api/tasks/" + task["task_id"])["task"]
                if state["status"] == "cancelled":
                    print("machine-control end-to-end running cancellation passed")
                    return
                time.sleep(.1)
            raise AssertionError(state)
        finally:
            if worker:
                worker.terminate(); worker.wait(timeout=5)
            center.terminate(); center.wait(timeout=5)

if __name__ == "__main__":
    main()
