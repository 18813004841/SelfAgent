#!/usr/bin/env python3
"""隔离验证工作台 HTTP 健康、配置和进程快照。"""
from __future__ import annotations
import os, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error, json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
server = root / "workbench" / "machine-dashboard-server" / "src" / "server.py"
with socket.socket() as reservation:
    reservation.bind(("127.0.0.1", 0))
    port = str(reservation.getsockname()[1])
env = {**os.environ, "LOCALAPPDATA": tempfile.mkdtemp(prefix="selfagent-wb-"), "MACHINE_DASHBOARD_PORT": port, "PYTHONPATH": str(server.parent)}
proc = subprocess.Popen([sys.executable, str(server)], cwd=server.parent.parent, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    deadline = time.time() + 10
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"workbench exited before readiness: {proc.returncode}")
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                health = json.loads(response.read())
            break
        except Exception:
            time.sleep(0.2)
    else:
        raise RuntimeError("workbench health timeout")
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/settings/storage", timeout=2)
    except urllib.error.HTTPError as error:
        assert error.code == 409
        settings = json.loads(error.read())
    else:
        raise AssertionError("server must not expose client storage settings")
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/processes", timeout=2) as response:
        processes = json.loads(response.read())
    assert health["ok"] and health["service"] == "machine-dashboard-server"
    assert settings["code"] == "client_local_only"
    assert "scheduler" in processes["processes"]
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/openai-agent/status", timeout=2) as response:
        agent_status = json.loads(response.read())
    assert agent_status["ok"] and agent_status["service"] == "openai-agent"
    assert agent_status["entry_exists"] and Path(agent_status["project_dir"]) == root / "AiAgent/AiProject/Codes/Agents/OpenAiAgent"
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/central-server/connections", timeout=2) as response:
        connections = json.loads(response.read())
    assert connections.get("ok") is True and isinstance(connections.get("ips"), list) and isinstance(connections.get("workers"), list)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/scheduler/status", timeout=2) as response:
        scheduler = json.loads(response.read())
    assert scheduler == {"ok": True, "service": "scheduler", "mode": "separate-process", "running": False, "pid": None}
    package = root / "Tools/machine-control/packages/central-client.zip"
    download_url = f"http://127.0.0.1:{port}/api/central-client/download"
    if package.is_file():
        with urllib.request.urlopen(download_url, timeout=3) as response:
            downloaded = response.read()
            assert response.headers.get("Content-Type") == "application/zip"
            assert response.headers.get("Content-Disposition") == 'attachment; filename="central-client.zip"'
        assert downloaded == package.read_bytes()
    else:
        try:
            urllib.request.urlopen(download_url, timeout=3)
        except urllib.error.HTTPError as error:
            assert error.code == 400
        else:
            raise AssertionError("missing client package unexpectedly downloaded")
    local_agent_package = root / "workbench/machine-dashboard-client/dist/workbench-machine-dashboard-client.zip"
    if local_agent_package.is_file():
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/local-agent/download", timeout=3) as response:
            assert response.headers.get("Content-Type") == "application/zip"
            assert response.read() == local_agent_package.read_bytes()
    def request(method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status, json.loads(response.read())
    tool_id = "validation-tool"
    for alias in ("/api/scheduler-tasks", "/api/scheduler-tasks/types"):
        assert request("POST", alias, {}) == request("GET", alias)
    review_before = request("GET", "/api/scheduler-tasks/code-review")
    review_alias = request("POST", "/api/scheduler-tasks/code-review", {"project_path": "must-not-save", "schedule_id": "must-not-create"})
    assert review_alias == review_before
    assert request("GET", "/api/scheduler-tasks/code-review") == review_before
    schedule_id = "validation-schedule"
    assert request("POST", "/api/tools", {"tool_id": tool_id, "entry": "validation"})[0] == 201
    try:
        request("POST", "/api/tools", {"tool_id": "missing-entry"})
    except urllib.error.HTTPError as error:
        assert error.code == 400
    else:
        raise AssertionError("invalid tool request unexpectedly succeeded")
    assert request("POST", "/api/schedules", {"id": schedule_id, "name": "Validation", "tool_id": tool_id})[0] == 201
    try:
        request("POST", "/api/schedules", {"id": "orphan", "name": "Orphan", "tool_id": "missing-tool"})
    except urllib.error.HTTPError as error:
        assert error.code == 400
    else:
        raise AssertionError("schedule with missing tool unexpectedly succeeded")
    assert all(item["id"] != "orphan" for item in request("GET", "/api/schedules")[1]["schedules"])
    false_id = "validation-disabled"
    assert request("POST", "/api/schedules", {"id": false_id, "name": "Disabled", "tool_id": tool_id, "enabled": "false"})[0] == 201
    assert request("GET", f"/api/schedules/{false_id}")[1]["schedule"]["enabled"] == 0
    try:
        request("POST", "/api/schedules", {"id": schedule_id, "name": "Duplicate", "tool_id": tool_id})
    except urllib.error.HTTPError as error:
        assert error.code == 409
    else:
        raise AssertionError("duplicate schedule unexpectedly succeeded")
    status, detail = request("GET", f"/api/schedules/{schedule_id}")
    assert status == 200 and detail["schedule"]["id"] == schedule_id
    assert request("POST", f"/api/schedules/{schedule_id}/cancel")[0] == 200
    assert request("POST", f"/api/schedules/{schedule_id}/disable")[0] == 200
    assert request("GET", "/api/schedules")[1]["schedules"]
    try:
        request("POST", "/api/schedules/unknown/action", {})
    except urllib.error.HTTPError as error:
        assert error.code == 404
    else:
        raise AssertionError("unknown schedule route unexpectedly succeeded")
    assert proc.poll() is None
    print("workbench HTTP validation passed")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait(timeout=5)
    assert proc.poll() is not None
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", int(port))) != 0, "validation port still listening"
