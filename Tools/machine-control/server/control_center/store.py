from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.models import Task, WorkerInfo, now_ms


class JsonStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.workers: Dict[str, WorkerInfo] = {}
        self.tasks: Dict[str, Task] = {}
        # Persistent cache of every machine/IP that has ever connected to this center.
        # This is the source for management UIs that need to show known machines even
        # after a worker process exits or has not heartbeated recently.
        self.machines: Dict[str, Dict[str, Any]] = {}
        # Raw client IP connection cache. This records any IP that reaches the
        # center HTTP server, even if it is not a registered worker yet.
        self.connections: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.workers = {
            k: WorkerInfo(**v) for k, v in data.get("workers", {}).items()
        }
        self.tasks = {
            k: Task(**v) for k, v in data.get("tasks", {}).items()
        }
        self.machines = dict(data.get("machines", {}))
        self.connections = dict(data.get("connections", {}))
        # Backfill cache from old stores that only had workers.
        for worker in self.workers.values():
            self._update_machine_cache(worker, "online")

    def _save(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        data = {
            "workers": {k: v.to_dict() for k, v in self.workers.items()},
            "tasks": {k: v.to_dict() for k, v in self.tasks.items()},
            "machines": self.machines,
            "connections": self.connections,
        }
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def record_connection(self, ip: str, path: str = "", user_agent: str = "") -> Dict[str, Any]:
        with self._lock:
            now = now_ms()
            item = dict(self.connections.get(ip, {}))
            item.update({
                "ip": ip,
                "first_seen_at": item.get("first_seen_at") or now,
                "last_seen_at": now,
                "last_path": path,
                "user_agent": user_agent,
            })
            self.connections[ip] = item
            self._save()
            return item

    def list_connections(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(self.connections.values(), key=lambda c: c.get("last_seen_at", 0), reverse=True)

    def _update_machine_cache(self, worker: WorkerInfo, login_state: str) -> Dict[str, Any]:
        now = now_ms()
        current_ips = list(worker.meta.get("local_ips", []) or [])
        primary_ip = next((ip for ip in current_ips if ip and not ip.startswith("127.")), "")
        # UI-facing machine identity is the machine IP, not the worker process name.
        # This prevents two different hosts that accidentally use the same --machine-id
        # from overwriting each other in the management UI.
        cache_id = primary_ip or worker.machine_id
        item = dict(self.machines.get(cache_id, {}))
        first_seen_at = item.get("first_seen_at") or worker.registered_at or now
        known_ips = list(item.get("known_ips", []))
        for ip in current_ips:
            if ip and ip not in known_ips:
                known_ips.append(ip)
        item.update({
            "machine_id": cache_id,
            "worker_id": worker.machine_id,
            "hostname": worker.hostname,
            "os": worker.os,
            "capabilities": list(worker.capabilities),
            "status": worker.status,
            "login_state": login_state,
            "first_seen_at": first_seen_at,
            "last_seen_at": worker.last_seen_at or now,
            "last_connected_at": now if login_state == "online" else item.get("last_connected_at"),
            "known_ips": known_ips,
            "current_ips": current_ips,
            "last_server": worker.meta.get("server"),
            "meta": dict(worker.meta),
        })
        self.machines[cache_id] = item
        # Remove stale pre-IP cache row for the same worker process name.
        if cache_id != worker.machine_id and worker.machine_id in self.machines:
            self.machines.pop(worker.machine_id, None)
        return item

    def register_worker(self, worker: WorkerInfo) -> WorkerInfo:
        with self._lock:
            old = self.workers.get(worker.machine_id)
            if old:
                worker.registered_at = old.registered_at
            worker.status = "online"
            worker.last_seen_at = now_ms()
            self.workers[worker.machine_id] = worker
            self._update_machine_cache(worker, "online")
            self._save()
            return worker

    def heartbeat(self, machine_id: str, meta: Optional[Dict[str, Any]] = None) -> WorkerInfo:
        with self._lock:
            worker = self.workers.get(machine_id)
            if not worker:
                raise KeyError(machine_id)
            worker.status = "online"
            worker.last_seen_at = now_ms()
            if meta:
                worker.meta.update(meta)
            self._update_machine_cache(worker, "online")
            self._save()
            return worker

    def list_machines(self, offline_after_ms: int = 15_000) -> List[Dict[str, Any]]:
        with self._lock:
            now = now_ms()
            # 1) Expire cached machine rows by their own heartbeat/connection time.
            # Rows can exist without an active worker object when two hosts reused
            # the same worker_id, so never rely on self.workers alone.
            for machine in self.machines.values():
                last_seen_at = int(machine.get("last_seen_at") or 0)
                if now - last_seen_at > offline_after_ms:
                    machine["status"] = "offline"
                    machine["login_state"] = "offline"

            # 2) Refresh currently known registered workers.
            for worker in self.workers.values():
                login_state = "online" if now - worker.last_seen_at <= offline_after_ms else "offline"
                if login_state == "offline":
                    worker.status = "offline"
                self._update_machine_cache(worker, login_state)

            # 3) Merge raw connection IPs. This is the central server's local record
            # of every IP that has ever reached it, even before/without successful
            # worker registration. The UI can therefore show connection-only hosts.
            known_machine_ips = set()
            for machine in self.machines.values():
                for ip in machine.get("known_ips", []) or []:
                    known_machine_ips.add(ip)
                for ip in machine.get("current_ips", []) or []:
                    known_machine_ips.add(ip)
            for ip, conn in self.connections.items():
                if not ip or ip.startswith("127.") or ip in known_machine_ips:
                    continue
                last_seen_at = int(conn.get("last_seen_at") or 0)
                login_state = "online" if now - last_seen_at <= offline_after_ms else "offline"
                item = dict(self.machines.get(ip, {}))
                item.update({
                    "machine_id": ip,
                    "worker_id": item.get("worker_id") or "",
                    "hostname": item.get("hostname") or "",
                    "os": item.get("os") or "",
                    "capabilities": item.get("capabilities") or ["connection"],
                    "status": login_state,
                    "login_state": login_state,
                    "first_seen_at": item.get("first_seen_at") or conn.get("first_seen_at") or last_seen_at,
                    "last_seen_at": last_seen_at,
                    "last_connected_at": conn.get("last_seen_at"),
                    "known_ips": [ip],
                    "current_ips": [ip] if login_state == "online" else [],
                    "last_server": "",
                    "meta": {"connection": conn},
                })
                self.machines[ip] = item

            self._save()
            return sorted(self.machines.values(), key=lambda m: (m.get("login_state") != "online", m.get("machine_id", "")))

    def list_workers(self) -> List[WorkerInfo]:
        with self._lock:
            return list(self.workers.values())

    def create_task(self, task: Task) -> Task:
        with self._lock:
            if task.machine_id not in self.workers:
                raise KeyError(f"unknown worker: {task.machine_id}")
            self.tasks[task.task_id] = task
            self._save()
            return task

    def list_tasks(self) -> List[Task]:
        with self._lock:
            return sorted(self.tasks.values(), key=lambda t: t.created_at, reverse=True)

    def get_task(self, task_id: str) -> Task:
        with self._lock:
            task = self.tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            return task

    def pick_next_task(self, machine_id: str, client_ip: str | None = None) -> Optional[Task]:
        with self._lock:
            queued = []
            for task in self.tasks.values():
                if task.machine_id != machine_id or task.status != "queued":
                    continue
                target_ip = task.payload.get("target_ip")
                # When multiple physical machines accidentally share one worker_id,
                # dashboard tasks include target_ip so only the matching requester can
                # pick the task. Normal tasks without target_ip keep old behaviour.
                if target_ip and client_ip and target_ip != client_ip:
                    continue
                queued.append(task)
            if not queued:
                return None
            queued.sort(key=lambda t: t.created_at)
            task = queued[0]
            task.status = "running"
            task.picked_at = now_ms()
            task.updated_at = now_ms()
            self._save()
            return task

    def finish_task(self, task_id: str, status: str, result: Dict[str, Any]) -> Task:
        with self._lock:
            task = self.get_task(task_id)
            task.status = status
            task.result = result
            task.finished_at = now_ms()
            task.updated_at = now_ms()
            self._save()
            return task
