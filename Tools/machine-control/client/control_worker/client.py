from __future__ import annotations

import argparse
import json
import platform
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Dict

from control_worker.executor import DEFAULT_ALLOWED_COMMANDS, execute_task


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str) -> None:
    print(f"[{ts()}] {message}", flush=True)


def get_local_ips() -> list[str]:
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        probe.close()
        if not ip.startswith("127.") and ip not in ips:
            ips.insert(0, ip)
    except Exception:
        pass
    return ips


def request(method: str, url: str, token: str, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--capability", action="append", default=["shell"])
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--allow-command", action="append", default=[])
    parser.add_argument("--verbose-heartbeat", action="store_true", help="Print every successful heartbeat")
    args = parser.parse_args()

    server = args.server.rstrip("/")
    allowed = set(DEFAULT_ALLOWED_COMMANDS) | set(args.allow_command)
    local_ips = get_local_ips()
    register_payload = {
        "machine_id": args.machine_id,
        "hostname": socket.gethostname(),
        "os": platform.platform(),
        "capabilities": sorted(set(args.capability)),
        "meta": {"allowed_commands": sorted(allowed), "local_ips": local_ips},
    }
    log("=" * 72)
    log("Machine Control Worker")
    log(f"machine_id       : {args.machine_id}")
    log(f"connect server   : {server}")
    log(f"local ips        : {', '.join(local_ips) if local_ips else 'unknown'}")
    log(f"capabilities     : {', '.join(sorted(set(args.capability)))}")
    log(f"allowed commands : {', '.join(sorted(allowed))}")
    log("registering...")
    register_result = request("POST", f"{server}/api/workers/register", args.token, register_payload)
    log("link status      : connected")
    log(json.dumps(register_result, ensure_ascii=False, indent=2))
    log("heartbeat        : silent; add --verbose-heartbeat to print every heartbeat")
    log("=" * 72)

    last_heartbeat = 0.0
    while True:
        try:
            now = time.time()
            if now - last_heartbeat > 15:
                local_ips = get_local_ips()
                request("POST", f"{server}/api/workers/heartbeat", args.token, {
                    "machine_id": args.machine_id,
                    "meta": {"ts": int(now), "server": server, "local_ips": local_ips},
                })
                if args.verbose_heartbeat:
                    log(f"heartbeat ok -> {server} local_ips={','.join(local_ips) if local_ips else 'unknown'}")
                last_heartbeat = now
            res = request("GET", f"{server}/api/workers/{args.machine_id}/tasks/next", args.token)
            task = res.get("task")
            if not task:
                time.sleep(args.poll_interval)
                continue
            log(f"picked task {task['task_id']} kind={task['kind']}")
            result = execute_task(task["kind"], task.get("payload", {}), allowed)
            status = "succeeded" if result.get("ok") else "failed"
            request("POST", f"{server}/api/tasks/{task['task_id']}/result", args.token, {
                "status": status,
                "result": result,
            })
            log(f"finished task {task['task_id']} status={status}")
        except urllib.error.HTTPError as e:
            log(f"http error: {e.code} {e.read().decode('utf-8', errors='ignore')}")
            time.sleep(args.poll_interval)
        except Exception as e:
            log(f"worker loop error: {e!r}")
            time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
