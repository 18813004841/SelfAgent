"""调度器链路测试任务。"""
from __future__ import annotations
import json
import time
from core.storage import connect
from .base import SchedulerBase

class TestScheduler(SchedulerBase):
    """用于验证调度链路的测试任务。"""
    scheduler_type = "test_scheduler"
    tool_id = "test-scheduler"

    def execute(self, args, context):
        # 模拟一个持续 10 秒的任务，每秒上报一次进度。
        for current in range(1, 11):
            time.sleep(1)
            context.progress(current, 10, f"测试任务进度 {current}/10")
        context.complete("succeeded", {"message": "测试任务执行完成", "progress": "10/10"})
        return {"message": "测试任务执行完成", "progress": "10/10"}

    def run_scheduled(self, schedule_id: str):
        """执行测试任务并写入统一运行记录。"""
        from .base import ScheduleContext
        started = time.time()
        db = connect()
        db.execute("UPDATE schedules SET last_run=?,last_status='running',progress_current=0,progress_total=10 WHERE id=?", (started, schedule_id))
        db.commit()

        def report_progress(current, total=None, message="", **details):
            db.execute("UPDATE schedules SET progress_current=?,progress_total=? WHERE id=?", (current, total or 10, schedule_id))
            db.commit()

        result = self.execute({}, ScheduleContext(schedule_id, report_progress, lambda *a, **k: None))
        with connect() as db:
            db.execute("INSERT INTO runs(schedule_id,started_at,finished_at,status,output) VALUES(?,?,?,?,?)", (schedule_id, started, time.time(), "succeeded", json.dumps(result, ensure_ascii=False)))
            db.execute("UPDATE schedules SET last_run=?,last_status='succeeded' WHERE id=?", (started, schedule_id))
        return result


