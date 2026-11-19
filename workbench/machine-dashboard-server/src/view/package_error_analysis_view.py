from . import router
from package_error_analysis.pipeline import create_task, get_task, list_tasks

@router.route("GET", "/api/package-error-analysis/tasks")
def list_view(ctx):
    ctx.request.send_json(200, {"ok": True, "tasks": list_tasks()})
    return True

@router.route("POST", "/api/package-error-analysis/tasks")
def create(ctx):
    text = str(ctx.body.get("input", "")).strip()
    if not text: raise ValueError("请输入 Jenkins 地址、飞书报告或日志内容")
    ctx.request.send_json(202, {"ok": True, "task": create_task(text)})
    return True

@router.route("GET", "/api/package-error-analysis/tasks/*")
def status(ctx):
    task_id = ctx.path.rsplit("/", 1)[-1]
    ctx.request.send_json(200, {"ok": True, "task": get_task(task_id)})
    return True
