"""保存一次任务执行的结构化日志。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

LOG_PATH = Path(__file__).with_name("logs") / "code_review_current.json"


def reset(task_id: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps({"task_id": task_id, "events": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def append(kind: str, message: str, **data: Any) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        current = json.loads(LOG_PATH.read_text(encoding="utf-8")) if LOG_PATH.is_file() else {"events": []}
    except (OSError, json.JSONDecodeError):
        current = {"events": []}
    current.setdefault("events", []).append({"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, "message": message, "data": data})
    LOG_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def read() -> dict[str, Any]:
    try:
        loaded = json.loads(LOG_PATH.read_text(encoding="utf-8")) if LOG_PATH.is_file() else {"events": []}
    except (OSError, json.JSONDecodeError):
        loaded = {"events": []}
    loaded.setdefault("events", [])
    return loaded
