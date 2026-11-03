from __future__ import annotations

import argparse
import platform
import socket
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Any, Dict, List

from common.models import Task, WorkerInfo
from control_center.http_util import parse_path, read_json, write_json
from control_center.store import JsonStore


class ControlHandler(BaseHTTPRequestHandler):
    server_version = "MachineControlCenter/0.1"

    def _auth_ok(self) -> bool:
        token = self.server.token  # type: ignore[attr-defined]
        if not token:
            return True
        return self.headers.get("Authorization", "") == f"Bearer {token}"

    def _require_auth(self) -> bool:
        if self._auth_ok():
            return True
        write_json(self, 401, {"ok": False, "error": "unauthorized"})
        return False

    def log_message(self, fmt: str, *args: Any) -> None:
        # 默认不打印每次 GET/POST 访问日志，避免 worker 轮询刷屏。
        # 需要排查请求时，启动 server 增加 --verbose-access-log。
        if getattr(self.server, "verbose_access_log", False):  # type: ignore[attr-defined]
            print(f"[{self.log_date_time_string()}] {self.client_address[0]} {fmt % args}", flush=True)

    def do_GET(self) -> None:
        if not self._require_auth() and self.path != "/health":
            return
        store: JsonStore = self.server.store  # type: ignore[attr-defined]
        path, parts = parse_path(self.path)
        store.record_connection(self.client_address[0], self.path, self.headers.get("User-Agent", ""))
        try:
            if path == "health":
                write_json(self, 200, {"ok": True, "service": "machine-control-center"})
                return
            if path == "api/workers":
                write_json(self, 200, {"ok": True, "workers": [w.to_dict() for w in store.list_workers()]})
                return
            if path == "api/machines":
                write_json(self, 200, {"ok": True, "machines": store.list_machines()})
                return
            if path == "api/connections":
                write_json(self, 200, {"ok": True, "connections": store.list_connections()})
                return
            if path == "api/tasks":
                write_json(self, 200, {"ok": True, "tasks": [t.to_dict() for t in store.list_tasks()]})
                return
            if len(parts) == 3 and parts[:2] == ["api", "tasks"]:
                task = store.get_task(parts[2])
                write_json(self, 200, {"ok": True, "task": task.to_dict()})
                return
            if len(parts) == 5 and parts[:2] == ["api", "workers"] and parts[3:] == ["tasks", "next"]:
                task = store.pick_next_task(parts[2], self.client_address[0])
                write_json(self, 200, {"ok": True, "task": task.to_dict() if task else None})
                return
            write_json(self, 404, {"ok": False, "error": "not found"})
        except KeyError as e:
            write_json(self, 404, {"ok": False, "error": str(e)})
        except Exception as e:
            write_json(self, 500, {"ok": False, "error": repr(e)})

    def do_POST(self) -> None:
        if not self._require_auth():
            return
        store: JsonStore = self.server.store  # type: ignore[attr-defined]
        path, parts = parse_path(self.path)
        store.record_connection(self.client_address[0], self.path, self.headers.get("User-Agent", ""))
        try:
            data = read_json(self)
            if path == "api/workers/register":
                worker = WorkerInfo(
                    machine_id=data["machine_id"],
                    hostname=data.get("hostname", ""),
                    os=data.get("os", ""),
                    capabilities=list(data.get("capabilities", [])),
                    meta=dict(data.get("meta", {})),
                )
                worker = store.register_worker(worker)
                print(
                    f"[worker connected] machine_id={worker.machine_id} "
                    f"hostname={worker.hostname} "
                    f"ips={','.join(worker.meta.get('local_ips', [])) or '-'} "
                    f"capabilities={','.join(worker.capabilities) or '-'}",
                    flush=True,
                )
                write_json(self, 200, {"ok": True, "worker": worker.to_dict()})
                return
            if path == "api/workers/heartbeat":
                before = store.workers.get(data["machine_id"])
                was_online = before.status == "online" if before else False
                worker = store.heartbeat(data["machine_id"], data.get("meta"))
                if not was_online:
                    print(
                        f"[worker heartbeat online] machine_id={worker.machine_id} "
                        f"hostname={worker.hostname} "
                        f"ips={','.join(worker.meta.get('local_ips', [])) or '-'}",
                        flush=True,
                    )
                write_json(self, 200, {"ok": True, "worker": worker.to_dict()})
                return
            if path == "api/tasks":
                task = Task(
                    machine_id=data["machine_id"],
                    kind=data.get("kind", "shell"),
                    payload=dict(data.get("payload", {})),
                )
                task = store.create_task(task)
                write_json(self, 200, {"ok": True, "task": task.to_dict()})
                return
            if len(parts) == 4 and parts[:2] == ["api", "tasks"] and parts[3] == "result":
                task = store.finish_task(parts[2], data.get("status", "succeeded"), dict(data.get("result", {})))
                write_json(self, 200, {"ok": True, "task": task.to_dict()})
                return
            write_json(self, 404, {"ok": False, "error": "not found"})
        except KeyError as e:
            write_json(self, 400, {"ok": False, "error": f"missing or unknown key: {e}"})
        except Exception as e:
            write_json(self, 500, {"ok": False, "error": repr(e)})


def _local_lan_ips() -> List[str]:
    ips: List[str] = []
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = item[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


def _print_connection_info(host: str, port: int, token: str) -> None:
    lan_ips = _local_lan_ips()
    print("=" * 64, flush=True)
    print("Machine Control Center - worker connection info", flush=True)
    print(f"Local URL : http://127.0.0.1:{port}", flush=True)
    if host in ("0.0.0.0", "::"):
        if lan_ips:
            for ip in lan_ips:
                print(f"Worker URL: http://{ip}:{port}", flush=True)
        else:
            print("Worker URL: <no LAN IPv4 detected>", flush=True)
    else:
        print(f"Worker URL: http://{host}:{port}", flush=True)
    print(f"Token     : {token}", flush=True)
    print("Use Worker URL as CENTRAL_URL on other machines; do not use 127.0.0.1 remotely.", flush=True)
    print("=" * 64, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default="dev-token")
    parser.add_argument("--store", default="data/control-center.json")
    parser.add_argument("--verbose-access-log", action="store_true", help="Print every HTTP GET/POST request")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ControlHandler)
    server.store = JsonStore(args.store)  # type: ignore[attr-defined]
    server.token = args.token  # type: ignore[attr-defined]
    server.verbose_access_log = args.verbose_access_log  # type: ignore[attr-defined]
    print(f"Machine Control Center listening on http://{args.host}:{args.port}", flush=True)
    print(f"Store: {args.store}", flush=True)
    _print_connection_info(args.host, args.port, args.token)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutting down")


if __name__ == "__main__":
    main()
