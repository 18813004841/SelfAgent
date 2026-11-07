"""代码检查任务的专属调度器。"""
from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from core.storage import connect
from .base import ScheduleContext, SchedulerBase
from .config import code_review_config
from .config import save_code_review_config
from .run_log import append, read, reset

TOOL_ROOT = Path(__file__).resolve().parents[4] / "Tools" / "code-review-agent"
_RUN_LOCK = threading.Lock()
_CANCEL = threading.Event()
class ReviewCancelled(RuntimeError):
    """用户请求终止当前代码检查。"""


class CodeReviewScheduler(SchedulerBase):
    """每天固定时间执行代码检查，并把工程配置传给工具。"""

    tool_id = "code-review-agent"
    run_at = "04:00"
    schedule_id = "code-review-daily"
    name = "代码检查"

    def display_data(self, args: Mapping[str, Any] | None = None) -> dict[str, str]:
        config = code_review_config()
        return {"project_path": config["project_path"], "branch": config["branch"], "skill_paths": config["skill_paths"], "allow_extra_rules": config["allow_extra_rules"], "failure_threshold": config["failure_threshold"], "run_at": self.run_at}

    def execute(self, args: Mapping[str, Any], context: ScheduleContext) -> Any:
        context.metadata["cancel"] = _CANCEL.is_set
        config = code_review_config()
        project_path = config["project_path"]
        branch = config["branch"]
        context.metadata.update(project_path=project_path, branch=branch, skill_paths=config["skill_paths"], allow_extra_rules=config["allow_extra_rules"])
        append("execute", "开始执行代码检查", project_path=project_path, branch=branch, skill_paths=config["skill_paths"], allow_extra_rules=config["allow_extra_rules"])
        context.progress(1, 4, "已读取工程配置", project_path=project_path, branch=branch, skill_paths=config["skill_paths"], allow_extra_rules=config["allow_extra_rules"])
        adapter = _load_tool_adapter()
        return adapter.execute({"project_path": project_path, "branch": branch, "skill_paths": config["skill_paths"], "allow_extra_rules": config["allow_extra_rules"], "failure_threshold": config["failure_threshold"], "cancel": _CANCEL.is_set}, context)

    def run_scheduled(self, schedule_id: str | None = None) -> Any:
        """由通用调度循环调用，负责记录本次执行状态。"""
        schedule_id = schedule_id or self.schedule_id
        started = time.time()
        reset(schedule_id)
        db = connect()
        db.execute("UPDATE schedules SET last_run=?,last_status='running',last_error=NULL,progress_current=0,progress_total=4,cancel_requested=0 WHERE id=?", (started, schedule_id))
        db.commit()
        finished = False

        def report_progress(current: int, total: int | None = None, message: str = "", details: dict | None = None, **extra: Any) -> None:
            info = dict(details or {})
            info.update(extra)
            append("progress", message or "进度更新", current=current, total=total, **info)
            if total:
                db.execute("UPDATE schedules SET progress_current=?,progress_total=? WHERE id=?", (current, total, schedule_id))
            else:
                db.execute("UPDATE schedules SET progress_current=? WHERE id=?", (current, schedule_id))
            db.commit()

        def finish(status: str = "succeeded", result: Any = None, details: dict | None = None, **extra: Any) -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            info = dict(details or {})
            info.update(extra)
            normalized = "succeeded" if status in {"succeeded", "passed", "skipped"} else "cancelled" if status == "cancelled" else "failed"
            append("result", "执行完成", status=normalized, result=result, **info)
            db.execute("INSERT INTO runs(schedule_id,started_at,finished_at,status,output,error) VALUES(?,?,?,?,?,?)", (schedule_id, started, time.time(), normalized, str(result), None if normalized == "succeeded" else str(result)))
            db.execute("UPDATE schedules SET last_status=?,progress_current=progress_total,last_error=? WHERE id=?", (normalized, None if normalized == "succeeded" else str(result), schedule_id))
            db.commit()

        context = ScheduleContext(run_id=schedule_id, report_progress=report_progress, finish=finish)
        try:
            result = self.execute({}, context)
            if not finished:
                finish("succeeded", result)
            return result
        except Exception as exc:
            if isinstance(exc, ReviewCancelled):
                append("result", "执行已终止", status="cancelled")
                if not finished:
                    finish("cancelled", {"error": "用户终止"})
                return {"status": "cancelled"}
            append("result", "执行失败", status="failed", error=repr(exc))
            if not finished:
                finish("failed", {"error": repr(exc)})
            raise


def sync_schedule() -> None:
    """确保代码检查调度器已注册到通用调度循环。"""
    scheduler = CodeReviewScheduler()
    config = scheduler.display_data()
    db = connect()
    db.execute("INSERT OR REPLACE INTO tools(tool_id,name,type,entry,workdir,enabled) VALUES(?,?,?,?,?,1)", (scheduler.tool_id, "代码检查", "scheduler", str(TOOL_ROOT / "code_review_scheduler.py"), str(TOOL_ROOT)))
    db.execute("INSERT INTO schedules(id,name,tool_id,schedule_type,schedule_expr,args_json,timeout,retry,enabled,next_run,task_type,dispatcher,progress_total) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,tool_id=excluded.tool_id,schedule_type=excluded.schedule_type,schedule_expr=excluded.schedule_expr,args_json=excluded.args_json", (scheduler.schedule_id, scheduler.name, scheduler.tool_id, "daily", scheduler.run_at, "{}", 900, 0, 1, scheduler.next_run_at(), "scheduled", "scheduler", 4))
    db.commit()
    return config


def task_payload() -> dict[str, Any]:
    """返回任务列表和任务页需要的配置、状态与本次日志。"""
    scheduler = CodeReviewScheduler()
    row = None
    try:
        db = connect()
        row = db.execute("SELECT last_status,progress_current,progress_total FROM schedules WHERE id=?", (scheduler.schedule_id,)).fetchone()
    except Exception:
        row = None
    data = scheduler.display_data()
    data.update({"id": scheduler.schedule_id, "name": scheduler.name, "tool_id": scheduler.tool_id, "last_status": row["last_status"] if row else None, "progress_current": row["progress_current"] if row else 0, "progress_total": row["progress_total"] if row else 4, "log": read()})
    return data


def update_task_config(project_path: str, branch: str, skill_paths: list[str] | str = ["skills"], allow_extra_rules: bool = False, failure_threshold: str = "high") -> dict[str, Any]:
    save_code_review_config('' if project_path.strip() == '未配置' else project_path, '' if branch.strip() == '未配置' else branch, skill_paths, allow_extra_rules, failure_threshold)
    return task_payload()


def start_task(project_path: str, branch: str, skill_paths: list[str] | str = ["skills"], allow_extra_rules: bool = False, failure_threshold: str = "high") -> dict[str, Any]:
    """保存当前配置并在后台执行一次代码检查。"""
    save_code_review_config('' if project_path.strip() == '未配置' else project_path, '' if branch.strip() == '未配置' else branch, skill_paths, allow_extra_rules, failure_threshold)
    _CANCEL.clear()
    if _RUN_LOCK.acquire(blocking=False):
        def worker() -> None:
            try:
                CodeReviewScheduler().run_scheduled()
            except Exception:
                pass
            finally:
                _RUN_LOCK.release()
        threading.Thread(target=worker, name="code-review-scheduler", daemon=True).start()
    return task_payload()


def stop_task() -> dict[str, Any]:
    """请求终止当前代码检查，正在进行的模型请求会在当前切片结束后停止。"""
    _CANCEL.set()
    append("result", "收到终止请求", status="cancelling")
    db = connect()
    db.execute("UPDATE schedules SET last_status='cancelling',cancel_requested=1 WHERE id=?", (CodeReviewScheduler.schedule_id,))
    db.commit()
    return task_payload()


def _load_tool_adapter():
    path = TOOL_ROOT / "code_review_scheduler.py"
    spec = importlib.util.spec_from_file_location("code_review_tool_scheduler", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载代码检查承接接口: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
