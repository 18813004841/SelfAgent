from pathlib import Path
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'src/schedulers/logs'
logger = get_logger('scheduler', DEBUG_LOG_DIR)

@router.route("GET", "/api/scheduler-tasks", "/api/scheduler-tasks/types")
@router.route("POST", "/api/scheduler/start", "/api/scheduler/stop", "/api/scheduler-tasks/create", "/api/scheduler-tasks/delete")
def handle(ctx):
    logger.debug("handling %s %s", ctx.method, ctx.path)
    import sys
    server = sys.modules.get("server") or sys.modules["__main__"]
    from schedulers.scheduler_controller import SchedulerController
    if ctx.path == "/api/scheduler-tasks/types":
        ctx.request.send_json(200, {"ok": True, "types": SchedulerController().types()})
    elif ctx.path == "/api/scheduler-tasks":
        ctx.request.send_json(200, {"ok": True, "tasks": SchedulerController().list()})
    elif ctx.path == "/api/scheduler-tasks/create":
        sid = SchedulerController().create(str(ctx.body["scheduler_type"]), str(ctx.body.get("name") or "新任务"), ctx.body.get("param", {}), int(ctx.body.get("run_type", 1)), str(ctx.body.get("run_time", "04:00")))
        ctx.request.send_json(201, {"ok": True, "id": sid})
    elif ctx.path == "/api/scheduler-tasks/delete":
        ctx.request.send_json(200, {"ok": SchedulerController().delete(str(ctx.body["id"]))})
    elif ctx.path == "/api/scheduler/start":
        h = server.PROCESS_MANAGER.start("scheduler"); ctx.request.send_json(200, {"ok": True, "pid": h.pid})
    elif ctx.path == "/api/scheduler/stop":
        server.PROCESS_MANAGER.stop("scheduler"); ctx.request.send_json(200, {"ok": True})
    return True



