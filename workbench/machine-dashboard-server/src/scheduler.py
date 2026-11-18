import time
import os
from datetime import datetime
# The scheduler is a separate process and cannot rely on server.py having
# initialized the shared log-session timestamp.
os.environ.setdefault("LOCAL_WORKBENCH_START_TIMESTAMP", datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
from concurrent.futures import ThreadPoolExecutor
_POOL = ThreadPoolExecutor(max_workers=3)
_PENDING = {}
from datetime import datetime, timedelta
from core.storage import decode_schedule, PID_PATH
from core.repositories import ScheduleRepository
from core.Log import AppLogger
from schedulers.code_review_scheduler import CodeReviewScheduler, sync_schedule
from schedulers.scheduler_controller import SchedulerController

logger = AppLogger("machine-dashboard.scheduler", "schedulers")
SCHEDULES = ScheduleRepository()

CONTROLLER = SchedulerController()


def next_run_at(schedule: dict, now: float) -> float | None:
    """按 run_type 计算下一次时间；执行一次的任务返回 None。"""
    run_type = int(schedule.get("run_type") or (1 if schedule.get("schedule_type") == "daily" else 2))
    if run_type == 2:
        return None
    hour, minute = (int(x) for x in str(schedule.get("run_time") or schedule.get("schedule_expr") or "04:00").split(":", 1))
    current = datetime.fromtimestamp(now)
    candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate.timestamp() <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def execute_schedule(schedule_id):
    """根据任务的 scheduler_type 分发给对应执行器。"""
    task = CONTROLLER.get(schedule_id)
    if not task:
        logger.error("找不到任务配置 schedule_id=%s", schedule_id)
        raise KeyError(schedule_id)
    scheduler = CONTROLLER.schedulers.get(task.get("scheduler_type"))
    if not scheduler:
        raise KeyError(f"未注册调度器: {task.get('scheduler_type')}")
    logger.info("任务到期，开始执行 schedule_id=%s scheduler_type=%s run_time=%s", schedule_id, task.get("scheduler_type"), task.get("run_time"))
    scheduler.set_param(task.get("param") or {})
    return scheduler.run_scheduled(schedule_id)

def due_loop(interval=5):
    logger.info("调度循环启动 interval=%s秒", interval)
    while True:
        now=time.time(); ids=SCHEDULES.due_ids(now)
        if ids:
            logger.info("发现到期任务 count=%s ids=%s", len(ids), ",".join(ids))
        for schedule_id in ids:
            try:
                pending = _PENDING.get(schedule_id)
                if pending is None:
                    _PENDING[schedule_id] = _POOL.submit(execute_schedule, schedule_id)
                    continue
                if not pending.done():
                    continue
                del _PENDING[schedule_id]
                pending.result()
                schedule = decode_schedule(SCHEDULES.get(schedule_id))
                nxt = next_run_at(schedule, now)
                if nxt is None:
                    SCHEDULES.disable(schedule_id)
                    logger.info("一次性任务已执行并停用 schedule_id=%s", schedule_id)
                else:
                    SCHEDULES.set_next_run(schedule_id, nxt)
                    logger.info("任务下次执行时间已更新 schedule_id=%s next_run=%s", schedule_id, datetime.fromtimestamp(nxt).isoformat(timespec="seconds"))
            except Exception:
                retry_at = now + 60
                SCHEDULES.set_next_run(schedule_id, retry_at)
                logger.exception("任务执行异常，已安排重试 schedule_id=%s retry_at=%s", schedule_id, datetime.fromtimestamp(retry_at).isoformat(timespec="seconds"))
        time.sleep(interval)


if __name__ == '__main__':
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(os.getpid()), encoding='utf-8')
    # 记录启动进程，便于确认后台调度器实例。
    logger.info("调度器已启动 script=%s pid=%s pid_file=%s", __file__, os.getpid(), PID_PATH)
    try:
        # 调度器启动时先把内置任务同步到 schedules 表，确保轮询可以找到待执行任务。
        config = sync_schedule()
        logger.info("内置任务已同步 schedule_id=%s run_at=%s", CodeReviewScheduler.schedule_id, config.get("run_at"))
        due_loop()
    except KeyboardInterrupt:
        logger.info("调度器收到停止信号，准备退出")
    except Exception:
        logger.exception("调度器发生未处理异常并退出")
        raise
    finally:
        PID_PATH.unlink(missing_ok=True)
        logger.info("调度器已退出")

