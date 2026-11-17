"""调度器链路测试任务。"""
from __future__ import annotations
import json
import time
from core.repositories import ScheduleRepository
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
        repository = ScheduleRepository()
        repository.mark_running(schedule_id, started, 10)

        def report_progress(current, total=None, message="", **details):
            repository.progress(schedule_id, current, total or 10)

        result = self.execute({}, ScheduleContext(schedule_id, report_progress, lambda *a, **k: None))
        repository.record_run(schedule_id, started, "succeeded", json.dumps(result, ensure_ascii=False))
        return result


