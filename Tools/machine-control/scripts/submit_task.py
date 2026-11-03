from __future__ import annotations

import argparse
import json
import time
import urllib.request


def req(method: str, url: str, token: str, data=None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    r = urllib.request.Request(url, data=body, method=method)
    r.add_header("Authorization", f"Bearer {token}")
    r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server", default="http://127.0.0.1:8765")
    p.add_argument("--token", default="dev-token")
    p.add_argument("--machine-id", required=True)
    p.add_argument("--command", required=True)
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument("--wait", action="store_true")
    args = p.parse_args()
    server = args.server.rstrip("/")
    created = req("POST", f"{server}/api/tasks", args.token, {
        "machine_id": args.machine_id,
        "kind": "shell",
        "payload": {"command": args.command, "timeout": args.timeout},
    })
    task_id = created["task"]["task_id"]
    print(json.dumps(created, ensure_ascii=False, indent=2))
    if args.wait:
        for _ in range(args.timeout + 10):
            task = req("GET", f"{server}/api/tasks/{task_id}", args.token)["task"]
            if task["status"] in ("succeeded", "failed", "cancelled"):
                print(json.dumps(task, ensure_ascii=False, indent=2))
                return
            time.sleep(1)
        raise SystemExit("timeout waiting for task")


if __name__ == "__main__":
    main()
