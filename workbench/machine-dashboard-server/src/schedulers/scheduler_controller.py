"""统一管理调度器实例及其数据库任务记录。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from core.storage import decode_schedule
from core.repositories import ScheduleRepository
from .base import SchedulerBase
from .code_review_scheduler import CodeReviewScheduler


from .test_scheduler import TestScheduler


class SchedulerController:
    """提供调度器注册、任务增删改查及执行控制的统一入口。"""

    # 所有可由页面选择的任务类型统一登记在这里。
    SCHEDULER_TYPES = (TestScheduler, CodeReviewScheduler)

    def __init__(self, schedulers: list[SchedulerBase] | None = None):
        items = schedulers if schedulers is not None else [cls() for cls in self.SCHEDULER_TYPES]
        self.schedulers = {type(item).scheduler_type: item for item in items}
        self.repository = ScheduleRepository()
        self.refresh()

    def types(self) -> list[dict[str, str]]:
        return [{"scheduler_type": key, "name": "测试任务" if key == "test_scheduler" else "代码检查器"} for key in self.schedulers]

    def refresh(self) -> list[dict[str, Any]]:
        self.tasks = [decode_schedule(row) for row in self.repository.list_all()]
        return self.tasks

    def list(self) -> list[dict[str, Any]]: return self.refresh()

    def get(self, task_id: str) -> dict[str, Any] | None:
        return next((x for x in self.refresh() if x["id"] == task_id), None)

    def create(self, scheduler_type: str, name: str, param: dict[str, Any], run_type: int = 1, run_time: str = "04:00", task_id: str | None = None) -> str:
        scheduler = self.schedulers[scheduler_type]
        task_id = task_id or scheduler.new_tool_id()
        scheduler._validate_run_at(run_time)
        if run_type not in (1, 2): raise ValueError("执行类型只能是 1 或 2")
        hour, minute = map(int, run_time.split(":"))
        now = datetime.now()
        initial = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if initial <= now: initial += timedelta(days=1)
        return self.repository.create({"id": task_id, "name": name, "tool_id": task_id, "schedule_type": "daily" if run_type == 1 else "once", "schedule_expr": run_time, "args_json": "{}", "timeout": 300, "retry": 0, "enabled": 1, "next_run": initial.timestamp(), "task_type": "scheduled", "dispatcher": "scheduler", "progress_total": 1, "scheduler_type": scheduler_type, "run_type": run_type, "run_time": run_time, "param_json": json.dumps(param, ensure_ascii=False)})

    def update(self, task_id: str, **fields: Any) -> bool:
        allowed = {k: fields[k] for k in ("name", "enabled", "run_type", "run_time", "param") if k in fields}
        if "param" in allowed: allowed["param_json"] = json.dumps(allowed.pop("param"), ensure_ascii=False)
        if not allowed: return False
        return self.repository.update(task_id, allowed)

    def delete(self, task_id: str) -> bool:
        return self.repository.delete(task_id)

    def execute(self, task_id: str) -> Any:
        task = self.get(task_id)
        scheduler = self.schedulers[task["scheduler_type"]]
        scheduler.set_param(task.get("param") or {})
        return scheduler.run_scheduled(task_id)

    def stop(self, task_id: str) -> bool:
        return self.repository.request_cancel(task_id)
