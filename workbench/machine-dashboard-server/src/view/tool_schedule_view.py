"""Tools and schedule HTTP contract, backed only by ScheduleRepository."""
from __future__ import annotations

import json
import time
import urllib.parse
import sqlite3

from core.repositories import ScheduleRepository
from core.storage import decode_schedule
from . import router


def _bool_value(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.strip().lower() in {"true", "1", "yes", "on"}:
        return True
    if isinstance(value, str) and value.strip().lower() in {"false", "0", "no", "off"}:
        return False
    raise ValueError("boolean value expected")


@router.route("GET", "/api/tools", "/api/schedules", "/api/schedules/*")
@router.route("POST", "/api/tools", "/api/schedules", "/api/schedules/*")
def handle(ctx):
    repository = ScheduleRepository()
    path = ctx.path
    if ctx.method == "GET" and path == "/api/tools":
        ctx.request.send_json(200, {"tools": [dict(row) for row in repository.list_tools()]})
    elif ctx.method == "GET" and path == "/api/schedules":
        ctx.request.send_json(200, {"schedules": [decode_schedule(row) for row in repository.list_all()]})
    elif ctx.method == "GET" and path.startswith("/api/schedules/"):
        sid = urllib.parse.unquote(path[len("/api/schedules/"):])
        row, runs = repository.schedule_detail(sid)
        if not row:
            ctx.request.send_json(404, {"ok": False, "error": "schedule not found"})
        else:
            item = decode_schedule(row); item["runs"] = [dict(run) for run in runs]
            ctx.request.send_json(200, {"schedule": item})
    elif ctx.method == "POST" and path == "/api/tools":
        body = ctx.body
        if not body.get("tool_id") or not body.get("entry"):
            ctx.request.send_json(400, {"ok": False, "error": "tool_id and entry are required"})
            return True
        try:
            enabled = int(_bool_value(body.get("enabled", True)))
        except (TypeError, ValueError):
            ctx.request.send_json(400, {"ok": False, "error": "enabled must be boolean"})
            return True
        repository.upsert_tool((body["tool_id"], body.get("name", body["tool_id"]), body.get("type", "local_process"), body["entry"], body.get("workdir"), enabled))
        ctx.request.send_json(201, {"ok": True, "tool_id": body["tool_id"]})
    elif ctx.method == "POST" and path == "/api/schedules":
        body = ctx.body; sid = body.get("id") or str(int(time.time() * 1000))
        if not body.get("name") or not body.get("tool_id"):
            ctx.request.send_json(400, {"ok": False, "error": "name and tool_id are required"})
            return True
        try:
            values = {"id": sid, "name": body["name"], "tool_id": body["tool_id"], "schedule_type": body.get("schedule_type", "interval"), "schedule_expr": body.get("schedule_expr", "60"), "args_json": json.dumps(body.get("args", {}), ensure_ascii=False), "timeout": int(body.get("timeout", 300)), "retry": int(body.get("retry", 0)), "enabled": int(_bool_value(body.get("enabled", True))), "next_run": time.time(), "task_type": body.get("task_type", "scheduled"), "dispatcher": body.get("dispatcher", "scheduler"), "progress_total": int(body.get("progress_total", 1)), "scheduler_type": None, "run_type": 1, "run_time": None, "param_json": "{}"}
            repository.create(values)
        except sqlite3.IntegrityError:
            ctx.request.send_json(409, {"ok": False, "error": "schedule already exists"})
            return True
        except (TypeError, ValueError, json.JSONDecodeError):
            ctx.request.send_json(400, {"ok": False, "error": "invalid schedule parameters"})
            return True
        ctx.request.send_json(201, {"ok": True, "id": sid})
    elif ctx.method == "POST" and path.endswith("/cancel"):
        sid = urllib.parse.unquote(path[len("/api/schedules/"):-len("/cancel")]); repository.request_cancel(sid); ctx.request.send_json(200, {"ok": True, "id": sid})
    elif ctx.method == "POST" and path.endswith(("/enable", "/disable")):
        sid = urllib.parse.unquote(path[len("/api/schedules/"):].rsplit("/", 1)[0]); enabled = 1 if path.endswith("/enable") else 0; repository.set_enabled(sid, enabled); ctx.request.send_json(200, {"ok": True, "enabled": bool(enabled)})
    else:
        ctx.request.send_json(404, {"ok": False, "error": "route not found"})
    return True
