from __future__ import annotations
import os, socket, subprocess, sys, tempfile, time
from pathlib import Path
root = Path(__file__).resolve().parents[1]
workbench = root / "workbench/machine-dashboard-server"
interpreter = workbench / ".venv/Scripts/python.exe"
if not interpreter.exists():
    interpreter = Path(sys.executable)
with tempfile.TemporaryDirectory(prefix="selfagent-conflict-") as td:
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0)); holder.listen(1)
        port = holder.getsockname()[1]
        env = {**os.environ, "LOCALAPPDATA": str(Path(td) / "user"), "MACHINE_DASHBOARD_HOST": "127.0.0.1", "MACHINE_DASHBOARD_PORT": str(port)}
        err_path = Path(td) / "stderr.log"
        with err_path.open("w+b") as err:
            proc = subprocess.Popen([str(interpreter), str(workbench / "src/server.py")], cwd=workbench, env=env, stdout=subprocess.DEVNULL, stderr=err)
            try:
                deadline = time.time() + 5
                while proc.poll() is None and time.time() < deadline:
                    time.sleep(0.1)
                if proc.poll() is None:
                    proc.terminate(); proc.wait(timeout=5)
                    raise AssertionError("server unexpectedly survived occupied port")
                err.flush(); err.seek(0)
                details = err.read().decode("utf-8", errors="replace")
                assert any(token in details for token in ("Address already in use", "WinError 10048", "WinError 10013", "10048", "10013")), details
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            finally:
                if proc.poll() is None:
                    proc.terminate(); proc.wait(timeout=5)
print("port conflict validation passed: external listener preserved")

