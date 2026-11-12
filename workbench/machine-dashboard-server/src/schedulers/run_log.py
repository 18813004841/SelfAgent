"""保存一次任务执行的结构化日志。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import re
from contextvars import ContextVar

LOG_DIR = Path(__file__).with_name("logs")
_CURRENT_TASK_ID = ContextVar("review_task_id", default="default")

def set_task(task_id: str) -> None:
    _CURRENT_TASK_ID.set(re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id)) or "default")

def _log_path(task_id=None) -> Path:
    key = re.sub(r"[^A-Za-z0-9_.-]", "_", str(task_id)) if task_id else _CURRENT_TASK_ID.get()
    return LOG_DIR / f"code_review_{key}.json"


def reset(task_id: str) -> None:
    set_task(task_id)
    path = _log_path(); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"task_id": task_id, "events": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def append(kind: str, message: str, **data: Any) -> None:
    path = _log_path(); path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"events": []}
    except (OSError, json.JSONDecodeError):
        current = {"events": []}
    current.setdefault("events", []).append({"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, "message": message, "data": data})
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def read(task_id=None) -> dict[str, Any]:
    try:
        path = _log_path(task_id)
        loaded = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"events": []}
    except (OSError, json.JSONDecodeError):
        loaded = {"events": []}
    loaded.setdefault("events", [])
    return loaded
