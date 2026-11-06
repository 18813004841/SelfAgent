import time, uuid, logging
from datetime import datetime, timedelta
from core.storage import connect, decode_schedule, PID_PATH
import os
from tasks.executor import run_tool
from schedulers.code_review_scheduler import CodeReviewScheduler

logger = logging.getLogger("machine-dashboard.scheduler")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(os.path.join(os.path.dirname(__file__), "..", "logs", "scheduler.log"), encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [feature=scheduler] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False

def execute_schedule(schedule_id):
    logger.info("schedule.begin schedule_id=%s", schedule_id)
    db = connect(); row = db.execute("SELECT tool_id FROM schedules WHERE id=?", (schedule_id,)).fetchone()
    if row and row["tool_id"] == CodeReviewScheduler.tool_id:
        return CodeReviewScheduler().run_scheduled(schedule_id)
    db=connect(); row=db.execute("SELECT s.*, t.name tool_name, t.type, t.entry, t.workdir, t.enabled tool_enabled FROM schedules s JOIN tools t ON t.tool_id=s.tool_id WHERE s.id=?",(schedule_id,)).fetchone()
    if not row: raise KeyError(schedule_id)
    schedule=decode_schedule(row); started=time.time(); run_id=str(uuid.uuid4())
    db.execute("UPDATE schedules SET last_run=?,last_status='running',last_error=NULL,progress_current=0,cancel_requested=0 WHERE id=?",(started,schedule_id)); db.commit()
    try:
        result=run_tool(schedule, schedule["args"], schedule["timeout"])
        cancelled = db.execute("SELECT cancel_requested FROM schedules WHERE id=?", (schedule_id,)).fetchone()[0]
        status = "cancelled" if cancelled else "succeeded"
        db.execute("INSERT INTO runs(schedule_id,started_at,finished_at,status,output) VALUES(?,?,?,?,?)",(schedule_id,started,time.time(),status,str(result)))
        db.execute("UPDATE schedules SET last_status=?,progress_current=progress_total WHERE id=?",(status,schedule_id)); db.commit(); logger.info("schedule.end schedule_id=%s status=%s", schedule_id, status); return result
    except Exception as exc:
        db.execute("INSERT INTO runs(schedule_id,started_at,finished_at,status,error) VALUES(?,?,?,?,?)",(schedule_id,started,time.time(),"failed",repr(exc)))
        db.execute("UPDATE schedules SET last_status='failed',last_error=? WHERE id=?",(repr(exc),schedule_id)); db.commit(); logger.exception("schedule.error schedule_id=%s", schedule_id); raise

def next_run_at(schedule: dict, now: float) -> float:
    if schedule.get("schedule_type") == "daily":
        hour, minute = (int(x) for x in str(schedule.get("schedule_expr", "04:00")).split(":", 1))
        current = datetime.fromtimestamp(now)
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate.timestamp() <= now: candidate += timedelta(days=1)
        return candidate.timestamp()
    if schedule.get("schedule_type") == "once": return now + 315360000
    try: return now + max(1, int(schedule.get("schedule_expr", 60)))
    except (TypeError, ValueError): return now + 60

def due_loop(interval=5):
    while True:
        db=connect(); now=time.time(); rows=db.execute("SELECT id FROM schedules WHERE enabled=1 AND (next_run IS NULL OR next_run<=?)",(now,)).fetchall()
        for row in rows:
            try:
                execute_schedule(row["id"])
                schedule = decode_schedule(db.execute("SELECT * FROM schedules WHERE id=?", (row["id"],)).fetchone())
                db.execute("UPDATE schedules SET next_run=? WHERE id=?",(next_run_at(schedule, now),row["id"]))
            except Exception: db.execute("UPDATE schedules SET next_run=? WHERE id=?",(now+60,row["id"]))
        db.commit(); time.sleep(interval)


if __name__ == '__main__':
    PID_PATH.parent.mkdir(parents=True, exist_ok=True); PID_PATH.write_text(str(os.getpid()), encoding='utf-8')
    logger.info("scheduler.started script=%s", __file__)
    try: due_loop()
    except KeyboardInterrupt: logger.info("scheduler.stopped reason=keyboard-interrupt")
    finally: PID_PATH.unlink(missing_ok=True)

