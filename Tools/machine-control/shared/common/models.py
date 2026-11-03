from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass
class WorkerInfo:
    machine_id: str
    hostname: str
    os: str
    capabilities: List[str]
    status: str = "online"
    registered_at: int = field(default_factory=now_ms)
    last_seen_at: int = field(default_factory=now_ms)
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Task:
    machine_id: str
    kind: str
    payload: Dict[str, Any]
    task_id: str = field(default_factory=lambda: new_id("task"))
    status: str = "queued"  # queued|running|succeeded|failed|cancelled
    created_at: int = field(default_factory=now_ms)
    updated_at: int = field(default_factory=now_ms)
    picked_at: Optional[int] = None
    finished_at: Optional[int] = None
    result: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
