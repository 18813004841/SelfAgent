"""Validate the optional machine-control MCP stdio handshake and tool catalog."""
from __future__ import annotations

import json
import argparse
import os
import subprocess
import sys
import queue
import threading
import socket
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "Tools" / "machine-control"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=Path(sys.executable),
                        help="Interpreter with the project's locked MCP extra installed")
    python = parser.parse_args().python.resolve()
    assert python.is_file(), f"missing interpreter: {python}"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(PROJECT / item) for item in ("server", "shared"))
    env["PYTHONNOUSERSITE"] = "1"
    reservation = socket.socket()
    reservation.bind(("127.0.0.1", 0))
    port = reservation.getsockname()[1]
    reservation.close()
    with tempfile.TemporaryDirectory(prefix="selfagent-mcp-") as temp:
        center = subprocess.Popen(
            [str(python), "-I", "-m", "control_center.server", "--host", "127.0.0.1",
             "--port", str(port), "--token", "mcp-validation", "--store", str(Path(temp) / "center.json")],
            cwd=PROJECT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.3)
                    break
                except OSError:
                    time.sleep(0.05)
            else:
                raise AssertionError("isolated central server did not become ready")
            server_url = f"http://127.0.0.1:{port}"
            worker = subprocess.Popen(
                [str(python), "-I", "-m", "control_worker.client", "--server", server_url,
                 "--machine-id", "mcp-worker", "--token", "mcp-validation",
                 "--poll-interval", ".1", "--allow-command", "echo"],
                cwd=PROJECT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                task_ids = _validate_protocol(python, env, server_url)
                persisted = json.loads((Path(temp) / "center.json").read_text(encoding="utf-8"))
                assert persisted["tasks"][task_ids[0]]["status"] == "succeeded", persisted
                assert persisted["tasks"][task_ids[1]]["status"] == "failed", persisted
            finally:
                worker.terminate()
                worker.wait(timeout=5)
        finally:
            center.terminate()
            center.wait(timeout=5)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with socket.socket() as probe:
                probe.settimeout(0.2)
                if probe.connect_ex(("127.0.0.1", port)) != 0:
                    break
            time.sleep(0.1)
        else:
            raise AssertionError("test center port still accepts connections")
        print("MCP owned center/Worker/server handles reaped; allocated port closed")


def _validate_protocol(python: Path, env: dict[str, str], server_url: str) -> tuple[str, str]:
    proc = subprocess.Popen(
        [str(python), "-I", "-m", "control_mcp.server", "--server", server_url, "--token", "mcp-validation"],
        cwd=PROJECT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )
    lines = queue.Queue()
    def read_output():
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)
    reader = threading.Thread(target=read_output, daemon=True)
    reader.start()
    try:
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "validation", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        for message in messages:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
            if "id" not in message:
                continue
            line = lines.get(timeout=15)
            assert line, "MCP server exited before protocol response"
            response = json.loads(line)
            assert response.get("jsonrpc") == "2.0" and "result" in response, response
            if message["id"] == 1:
                assert response["result"]["protocolVersion"] == "2025-03-26"
            else:
                names = {item["name"] for item in response["result"]["tools"]}
                assert {"health", "list_workers", "list_tasks", "submit_shell_task"} <= names, names
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "health", "arguments": {}}}) + "\n")
        proc.stdin.flush()
        response = json.loads(lines.get(timeout=15))
        assert response["result"]["structuredContent"]["result"]["ok"] is True, response
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "submit_shell_task_and_wait", "arguments": {"machine_id": "mcp-worker", "command": "echo mcp-validation", "timeout": 10}}}) + "\n")
        proc.stdin.flush()
        response = json.loads(lines.get(timeout=20))
        result = response["result"]["structuredContent"]["result"]
        assert result["task"]["status"] == "succeeded", response
        assert "mcp-validation" in result["task"]["result"]["stdout"], response
        success_id = result["task"]["task_id"]
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "submit_shell_task_and_wait", "arguments": {"machine_id": "mcp-worker", "command": "definitely-not-allowed", "timeout": 10}}}) + "\n")
        proc.stdin.flush()
        response = json.loads(lines.get(timeout=20))
        rejected = response["result"]["structuredContent"]["result"]
        assert rejected["task"]["status"] == "failed", response
        assert rejected["task"]["result"]["exit_code"] == 126, response
        assert "not allowed" in rejected["task"]["result"]["stderr"], response
        print("machine-control MCP handshake, health, echo success, allowlist rejection and persistence passed")
        return success_id, rejected["task"]["task_id"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        reader.join(timeout=2)


if __name__ == "__main__":
    main()
