"""隔离目录下验证工作台、machine-control 和 AiAgent 的联合运行边界。

脚本只管理本次创建的子进程，并在退出时逐一关闭；不会按端口或 PID 猜测并终止外部进程。
"""
from __future__ import annotations

import os, socket, subprocess, tempfile, time, urllib.request, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

def wait_http(url: str, timeout=12, token=None) -> dict:
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
            with urllib.request.urlopen(request, timeout=1) as r:
                return json.loads(r.read().decode())
        except Exception as exc:
            last = exc; time.sleep(.2)
    raise RuntimeError(f"service did not become ready: {url}: {last}")

def main() -> None:
    workbench = ROOT / "workbench/machine-dashboard-server"
    machine = ROOT / "Tools/machine-control"
    agent = ROOT / "AiAgent/AiProject/Codes/Agents/OpenAiAgent"
    wb_py = workbench / ".venv/Scripts/python.exe"
    mc_py = machine / ".venv/Scripts/python.exe"
    agent_py = agent / ".venv/Scripts/python.exe"
    for p in (wb_py, mc_py, agent_py):
        if not p.exists(): raise SystemExit(f"missing project interpreter: {p}")
    center_port, wb_port = free_port(), free_port()
    token = "joint-validation-token"
    procs: list[subprocess.Popen] = []
    with tempfile.TemporaryDirectory(prefix="selfagent-joint-", ignore_cleanup_errors=True) as td:
        data = Path(td)
        center_store = data / "machine-control.json"
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(machine/"server"), str(machine/"shared"), str(machine/"client")])
        try:
            procs.append(subprocess.Popen([str(mc_py), "-m", "control_center.server", "--host", "127.0.0.1", "--port", str(center_port), "--token", token, "--store", str(center_store)], cwd=machine, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            wait_http(f"http://127.0.0.1:{center_port}/health")
            worker_env = env | {"PYTHONPATH": env["PYTHONPATH"]}
            procs.append(subprocess.Popen([str(mc_py), "-m", "control_worker.client", "--server", f"http://127.0.0.1:{center_port}", "--machine-id", "joint-validation-worker", "--token", token, "--poll-interval", "0.2"], cwd=machine, env=worker_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            end = time.time() + 10
            while time.time() < end:
                try:
                    workers = wait_http(f"http://127.0.0.1:{center_port}/api/workers", timeout=1, token=token).get("workers", [])
                    if any(w.get("machine_id") == "joint-validation-worker" for w in workers): break
                except Exception: pass
                time.sleep(.2)
            else: raise RuntimeError("worker did not register")
            wb_env = os.environ.copy(); wb_env.update({"LOCALAPPDATA":str(data/"user"), "MACHINE_DASHBOARD_HOST":"127.0.0.1", "MACHINE_DASHBOARD_PORT":str(wb_port), "MACHINE_CONTROL_PORT":str(center_port), "MACHINE_CONTROL_TOKEN":token, "MACHINE_CONTROL_SERVER_URL":f"http://127.0.0.1:{center_port}", "PYTHONPATH":str(workbench/"src")})
            procs.append(subprocess.Popen([str(wb_py), "src/server.py"], cwd=workbench, env=wb_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            wait_http(f"http://127.0.0.1:{wb_port}/api/health")
            connections = wait_http(f"http://127.0.0.1:{wb_port}/api/central-server/connections")
            assert any(item.get("machine_id") == "joint-validation-worker" for item in connections.get("workers", [])), connections
            agent_env = os.environ.copy()
            agent_env["PYTHONPATH"] = str(agent)
            subprocess.run([str(agent_py), "-m", "codex_agent.cli", "--help"], cwd=agent, env=agent_env, check=True, stdout=subprocess.DEVNULL)
            print("joint runtime validation passed: center, worker, workbench, agent CLI")
        finally:
            for p in reversed(procs):
                if p.poll() is None: p.terminate()
            for p in reversed(procs):
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=2)
            if any(p.poll() is None for p in procs): raise RuntimeError("child process remained alive")

if __name__ == "__main__": main()
