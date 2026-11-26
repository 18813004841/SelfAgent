from . import router
from project37.preflight import check
from project37.settings import get_settings, save_settings
from .logging import get_logger

logger = get_logger("project37")

@router.route("POST", "/api/server-maintenance/project37/preflight")
def preflight(ctx):
    result = check(ctx.body)
    ctx.request.send_json(200, {"ok": True, "result": result})
    return True

@router.route("GET", "/api/server-maintenance/project37/settings")
def get_config(ctx):
    ctx.request.send_json(200, {"ok": True, "settings": get_settings(ctx.request.current_user["id"])})
    return True

@router.route("POST", "/api/server-maintenance/project37/settings")
def save_config(ctx):
    user_id = ctx.request.current_user["id"]
    logger.info("project37.settings.save.begin user_id=%s", user_id)
    try:
        result = save_settings(user_id, ctx.body)
    except Exception:
        logger.error("project37.settings.save.failed user_id=%s", user_id)
        raise
    logger.info("project37.settings.save.end user_id=%s", user_id)
    ctx.request.send_json(200, {"ok": True, "settings": result})
    return True

@router.route("POST", "/api/server-maintenance/project37/tasks")
def start_task(ctx):
    from project37.workflow import create_task
    ctx.request.send_json(202, {"ok": True, "task": create_task(ctx.request.current_user["id"], ctx.body)})
    return True

@router.route("GET", "/api/server-maintenance/project37/tasks/latest")
def latest_task(ctx):
    from project37.workflow import latest
    ctx.request.send_json(200, {"ok": True, "task": latest(ctx.request.current_user["id"])})
    return True

@router.route("GET", "/api/server-maintenance/project37/tasks/*")
def task_status(ctx):
    from project37.workflow import get_task
    ctx.request.send_json(200, {"ok": True, "task": get_task(ctx.request.current_user["id"], ctx.path.rsplit("/", 1)[-1])})
    return True

@router.route("POST", "/api/server-maintenance/project37/continue")
def continue_task(ctx):
    from project37.workflow import resume_task
    if not ctx.request.current_user.get("is_admin"):
        raise RuntimeError("仅管理员可继续处理合并冲突")
    task_id = ctx.body.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("缺少任务 ID")
    ctx.request.send_json(202, {"ok": True, "task": resume_task(ctx.request.current_user["id"], task_id)})
    return True

@router.route("POST", "/api/server-maintenance/project37/push")
def push(ctx):
    from project37.workflow import push_task
    task_id = ctx.body.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("缺少任务 ID")
    ctx.request.send_json(202, {"ok": True, "task": push_task(ctx.request.current_user["id"], task_id)})
    return True
