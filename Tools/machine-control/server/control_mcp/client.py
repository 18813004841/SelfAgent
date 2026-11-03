from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Dict, Optional


class ControlCenterClient:
    def __init__(self, server: str, token: str):
        self.server = server.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        body = None if data is None else json.dumps(data).encode("utf-8")
        req = urllib.request.Request(f"{self.server}{path}", data=body, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def health(self) -> Dict[str, Any]:
        return self.request("GET", "/health")

    def list_workers(self) -> Dict[str, Any]:
        return self.request("GET", "/api/workers")

    def list_tasks(self) -> Dict[str, Any]:
        return self.request("GET", "/api/tasks")

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self.request("GET", f"/api/tasks/{task_id}")

    def submit_shell_task(self, machine_id: str, command: str, timeout: int = 60, cwd: str | None = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"command": command, "timeout": timeout}
        if cwd:
            payload["cwd"] = cwd
        return self.request("POST", "/api/tasks", {
            "machine_id": machine_id,
            "kind": "shell",
            "payload": payload,
        })

    def wait_task(self, task_id: str, timeout: int = 120, interval: float = 1.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = self.get_task(task_id)["task"]
            if task["status"] in ("succeeded", "failed", "cancelled"):
                return {"ok": True, "task": task}
            time.sleep(interval)
        return {"ok": False, "error": "timeout", "task": self.get_task(task_id).get("task")}
