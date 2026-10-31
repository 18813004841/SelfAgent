import time, uuid
from core.storage import connect, decode_schedule, PID_PATH
import os
from tasks.executor import run_tool

def execute_schedule(schedule_id):
    db=connect(); row=db.execute("SELECT s.*, t.name tool_name, t.type, t.entry, t.workdir, t.enabled tool_enabled FROM schedules s JOIN tools t ON t.tool_id=s.tool_id WHERE s.id=?",(schedule_id,)).fetchone()
    if not row: raise KeyError(schedule_id)
    schedule=decode_schedule(row); started=time.time(); run_id=str(uuid.uuid4())
    db.execute("UPDATE schedules SET last_run=?,last_status='running',last_error=NULL WHERE id=?",(started,schedule_id)); db.commit()
    try:
        result=run_tool(schedule, schedule["args"], schedule["timeout"])
        db.execute("INSERT INTO runs(schedule_id,started_at,finished_at,status,output) VALUES(?,?,?,?,?)",(schedule_id,started,time.time(),"succeeded",str(result)))
        db.execute("UPDATE schedules SET last_status='succeeded' WHERE id=?",(schedule_id,)); db.commit(); return result
    except Exception as exc:
        db.execute("INSERT INTO runs(schedule_id,started_at,finished_at,status,error) VALUES(?,?,?,?,?)",(schedule_id,started,time.time(),"failed",repr(exc)))
        db.execute("UPDATE schedules SET last_status='failed',last_error=? WHERE id=?",(repr(exc),schedule_id)); db.commit(); raise

def due_loop(interval=5):
    while True:
        db=connect(); now=time.time(); rows=db.execute("SELECT id FROM schedules WHERE enabled=1 AND (next_run IS NULL OR next_run<=?)",(now,)).fetchall()
        for row in rows:
            try:
                execute_schedule(row["id"])
                db.execute("UPDATE schedules SET next_run=? WHERE id=?",(now+60,row["id"]))
            except Exception: db.execute("UPDATE schedules SET next_run=? WHERE id=?",(now+60,row["id"]))
        db.commit(); time.sleep(interval)


if __name__ == '__main__':
    PID_PATH.parent.mkdir(parents=True, exist_ok=True); PID_PATH.write_text(str(os.getpid()), encoding='utf-8')
    print(f"Scheduler started: {__file__}", flush=True)
    try: due_loop()
    except KeyboardInterrupt: print("Scheduler stopped.", flush=True)
    finally: PID_PATH.unlink(missing_ok=True)

