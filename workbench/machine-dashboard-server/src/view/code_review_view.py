from pathlib import Path
from . import router
from core.Log.log_helper import get_view_logger, get_code_review_logger
from core.Log import LogLevel

view_logger = get_view_logger()
logger = get_code_review_logger("code_review")


def read_code_review_config(schedule_id=None):
    """读取代码检查页面的完整配置。"""
    from schedulers.code_review_scheduler import task_payload, CodeReviewScheduler
    schedule_id = schedule_id or CodeReviewScheduler.schedule_id
    view_logger.info("读取代码检查完整配置 schedule_id=%s", schedule_id)
    logger.info("读取代码检查完整配置 schedule_id=%s", schedule_id)
    return task_payload(schedule_id)


def read_code_review_status(schedule_id=None):
    """读取代码检查执行状态和日志，供轮询使用。"""
    from schedulers.code_review_scheduler import task_status_payload, CodeReviewScheduler
    schedule_id = schedule_id or CodeReviewScheduler.schedule_id
    view_logger.debug("读取代码检查运行状态 schedule_id=%s", schedule_id)
    logger.debug("读取代码检查运行状态 schedule_id=%s", schedule_id)
    return task_status_payload(schedule_id)

@router.route("GET", "/api/scheduler-tasks/code-review", "/api/scheduler-tasks/code-review/*")
@router.route("POST", "/api/scheduler-tasks/code-review/run", "/api/scheduler-tasks/code-review/stop", "/api/scheduler-tasks/code-review/config", "/api/scheduler-tasks/code-review/clear-history", "/api/scheduler-tasks/code-review/choose", "/api/scheduler-tasks/code-review/open", "/api/code-review/setup")
def handle(ctx):
    """代码检查页面：读取、启动、停止、保存配置及目录操作。"""
    view_logger.log(LogLevel.DEBUG, "handling %s %s", ctx.method, ctx.path)
    logger.log(LogLevel.DEBUG, "handling %s %s", ctx.method, ctx.path)
    import os
    from pathlib import Path
    from schedulers.code_review_scheduler import CodeReviewScheduler, clear_review_history, start_task, stop_task, update_task_config
    if ctx.method == "GET":
        sid = None if ctx.path == "/api/scheduler-tasks/code-review" else ctx.path.rsplit("/", 1)[-1]
        # 带 refresh=status 时只读取运行状态和执行日志，避免轮询反复读取配置。
        if ctx.request.path.find("refresh=status") >= 0:
            ctx.request.send_json(200, {"ok": True, "task": read_code_review_status(sid)})
        else:
            ctx.request.send_json(200, {"ok": True, "task": read_code_review_config(sid)})
    elif ctx.path.endswith("/run"):
        task = start_task(str(ctx.body.get("project_path", "")), str(ctx.body.get("branch", "")), ctx.body.get("skill_paths", ["skills"]), bool(ctx.body.get("allow_extra_rules", False)), str(ctx.body.get("failure_threshold", "high")), str(ctx.body.get("schedule_id") or CodeReviewScheduler.schedule_id))
        ctx.request.send_json(200, {"ok": True, "task": task})
    elif ctx.path.endswith("/stop"):
        ctx.request.send_json(200, {"ok": True, "task": stop_task(str(ctx.body.get("schedule_id") or CodeReviewScheduler.schedule_id))})
    elif ctx.path.endswith("/config"):
        task = update_task_config(str(ctx.body.get("project_path", "")), str(ctx.body.get("branch", "")), ctx.body.get("skill_paths", ["skills"]), bool(ctx.body.get("allow_extra_rules", False)), str(ctx.body.get("failure_threshold", "high")), str(ctx.body.get("schedule_id") or CodeReviewScheduler.schedule_id))
        ctx.request.send_json(200, {"ok": True, "task": task})
    elif ctx.path.endswith("/clear-history"):
        cleared = clear_review_history(str(ctx.body.get("project_path", "")), str(ctx.body.get("branch", "")))
        ctx.request.send_json(200, {"ok": True, "cleared": cleared, "task": read_code_review_config(str(ctx.body.get("schedule_id") or CodeReviewScheduler.schedule_id))})
    elif ctx.path.endswith("/choose"):
        import tkinter as tk
        from tkinter import filedialog
        current = str(ctx.body.get("current_path") or task_payload().get("project_path") or Path.home())
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="选择工程目录", initialdir=current if Path(current).is_dir() else str(Path.home())); root.destroy()
        ctx.request.send_json(200, {"ok": True, "project_path": str(Path(selected).resolve()) if selected else ""})
    elif ctx.path.endswith("/open"):
        target = Path(str(ctx.body.get("project_path", "")).strip()).expanduser()
        if not target.is_dir(): raise ValueError("工程目录不存在")
        os.startfile(target); ctx.request.send_json(200, {"ok": True})
    elif ctx.path == "/api/code-review/setup":
        ctx.request.send_json(200, {"ok": True, "task": update_task_config(str(ctx.body.get("project_path", "")), str(ctx.body.get("branch", "main")), ctx.body.get("skill_paths", ["skills"]), False, "high", str(ctx.body.get("schedule_id") or CodeReviewScheduler.schedule_id))})
    return True




