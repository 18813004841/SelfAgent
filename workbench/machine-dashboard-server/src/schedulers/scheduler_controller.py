"""统一管理调度器实例及其数据库任务记录。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from core.storage import connect, decode_schedule
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
        self.refresh()

    def types(self) -> list[dict[str, str]]:
        return [{"scheduler_type": key, "name": "测试任务" if key == "test_scheduler" else "代码检查器"} for key in self.schedulers]

    def refresh(self) -> list[dict[str, Any]]:
        db = connect()
        self.tasks = [decode_schedule(row) for row in db.execute("SELECT * FROM schedules ORDER BY name")]
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
        db = connect()
        db.execute("INSERT INTO schedules(id,name,tool_id,schedule_type,schedule_expr,args_json,timeout,retry,enabled,next_run,task_type,dispatcher,progress_total,scheduler_type,run_type,run_time,param_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (task_id, name, task_id, "daily" if run_type == 1 else "once", run_time, "{}", 300, 0, 1, initial.timestamp(), "scheduled", "scheduler", 1, scheduler_type, run_type, run_time, json.dumps(param, ensure_ascii=False)))
        db.commit(); return task_id

    def update(self, task_id: str, **fields: Any) -> bool:
        allowed = {k: fields[k] for k in ("name", "enabled", "run_type", "run_time", "param") if k in fields}
        if "param" in allowed: allowed["param_json"] = json.dumps(allowed.pop("param"), ensure_ascii=False)
        if not allowed: return False
        db = connect(); db.execute("UPDATE schedules SET " + ",".join(f"{k}=?" for k in allowed) + " WHERE id=?", (*allowed.values(), task_id)); db.commit(); return db.total_changes > 0

    def delete(self, task_id: str) -> bool:
        db = connect(); db.execute("DELETE FROM schedules WHERE id=?", (task_id,)); db.commit(); return db.total_changes > 0

    def execute(self, task_id: str) -> Any:
        task = self.get(task_id)
        scheduler = self.schedulers[task["scheduler_type"]]
        scheduler.set_param(task.get("param") or {})
        return scheduler.run_scheduled(task_id)

    def stop(self, task_id: str) -> bool:
        db = connect(); db.execute("UPDATE schedules SET cancel_requested=1,last_status='cancelling' WHERE id=?", (task_id,)); db.commit(); return db.total_changes > 0
