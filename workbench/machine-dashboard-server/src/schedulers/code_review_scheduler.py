"""代码检查任务的专属调度器。"""
from __future__ import annotations

import importlib.util
import json
import re
import os
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from core.repositories import ScheduleRepository
from core.settings import get_settings
from core.Log import AppLogger
from .base import ScheduleContext, SchedulerBase
from .config import code_review_config
from .review_notification_settings import get_webhook
from .run_log import append, read, reset, set_task

TOOL_ROOT = Path(__file__).resolve().parents[2] / "tools" / "code-review-agent"
CODE_REVIEW_DATA_ROOT = Path(os.environ.get("WORKBENCH_CODE_REVIEW_DATA_DIR", str(get_settings().output_dir / "code-review")))
os.environ.setdefault("WORKBENCH_CODE_REVIEW_DATA_DIR", str(CODE_REVIEW_DATA_ROOT))

logger = AppLogger("code-review-scheduler", "code_review_scheduler")
class ReviewCancelled(RuntimeError):
    """用户请求终止当前代码检查。"""


class CodeReviewScheduler(SchedulerBase):
    """每天固定时间执行代码检查，并把工程配置传给工具。"""

    tool_id = "code-review-agent"
    run_at = "04:00"
    schedule_id = "code-review-daily"
    name = "代码检查"
    scheduler_type = "code_review_scheduler"

    def get_param(self) -> dict[str, Any]:
        """把代码检查专属配置写入任务 param。"""
        config = code_review_config()
        logger.debug("get_param project_path=%s branch=%s", config.get("project_path"), config.get("branch"))
        return {"project_path": config["project_path"], "branch": config["branch"], "skill_paths": config["skill_paths"], "allow_extra_rules": config["allow_extra_rules"], "failure_threshold": config["failure_threshold"]}

    def set_param(self, param: Mapping[str, Any] | None) -> None:
        """从任务 param 恢复代码检查配置。"""
        logger.debug("set_param keys=%s", list(param or {}))
        return None

    def display_data(self, args: Mapping[str, Any] | None = None) -> dict[str, str]:
        # 空字典代表当前任务尚未配置，不能回退到共享配置。
        config = dict(self.get_param() if args is None else args)
        logger.debug("display_data project_path=%s branch=%s", config.get("project_path"), config.get("branch"))
        return {"project_path": config.get("project_path", ""), "branch": config.get("branch", ""), "skill_paths": config.get("skill_paths", []), "allow_extra_rules": config.get("allow_extra_rules", False), "failure_threshold": config.get("failure_threshold", "high"), "run_at": self.run_at}

    def execute(self, args: Mapping[str, Any], context: ScheduleContext) -> Any:
        logger.debug("execute.begin run_id=%s cancel=%s", context.run_id, context.metadata["cancel"]())
        config = dict(args)
        if not str(config.get("project_path") or "").strip():
            raise ValueError("当前任务尚未配置工程路径，请先保存配置")
        project_path = config["project_path"]
        branch = config["branch"]
        context.metadata.update(project_path=project_path, branch=branch, skill_paths=config["skill_paths"], allow_extra_rules=config["allow_extra_rules"])
        append("execute", "开始执行代码检查", implementation="codex-review-v3", project_path=project_path, branch=branch, skill_paths=config["skill_paths"], allow_extra_rules=config["allow_extra_rules"])
        logger.info("开始执行代码检查 schedule_id=%s project_path=%s branch=%s", context.run_id, project_path, branch)
        context.progress(1, 4, "已读取工程配置", project_path=project_path, branch=branch, skill_paths=config["skill_paths"], allow_extra_rules=config["allow_extra_rules"])
        adapter = _load_tool_adapter()
        logger.debug("execute.call_adapter run_id=%s", context.run_id)
        try:
            webhook = get_webhook()
        except ValueError:
            logger.warning("review.feishu.config_unavailable")
            webhook = ""
        return adapter.execute({"project_path": project_path, "branch": branch, "skill_paths": config["skill_paths"], "allow_extra_rules": config["allow_extra_rules"], "failure_threshold": config["failure_threshold"], "feishu_webhook": webhook, "cancel": context.metadata["cancel"]}, context)

    def run_scheduled(self, schedule_id: str | None = None) -> Any:
        from .execution_guard import claim, release
        schedule_id = schedule_id or self.schedule_id
        token = claim(schedule_id)
        try:
            return self._run_claimed(schedule_id)
        finally:
            release(token)

    def _run_claimed(self, schedule_id: str | None = None) -> Any:
        """由通用调度循环调用，负责记录本次执行状态。"""
        logger.debug("run_scheduled.begin schedule_id=%s", schedule_id or self.schedule_id)
        schedule_id = schedule_id or self.schedule_id
        set_task(schedule_id)
        started = time.time()
        reset(schedule_id)
        repository = ScheduleRepository()
        repository.mark_code_review_running(schedule_id, started)
        logger.info("任务状态已更新为执行中 schedule_id=%s", schedule_id)
        finished = False

        def report_progress(current: int, total: int | None = None, message: str = "", details: dict | None = None, **extra: Any) -> None:
            info = dict(details or {})
            info.update(extra)
            append("progress", message or "进度更新", current=current, total=total, **info)
            logger.debug("进度更新 schedule_id=%s current=%s total=%s message=%s", schedule_id, current, total, message)
            repository.mark_code_review_progress(schedule_id, current, total)

        def finish(status: str = "succeeded", result: Any = None, details: dict | None = None, **extra: Any) -> None:
            nonlocal finished
            logger.debug("finish.begin schedule_id=%s status=%s finished=%s", schedule_id, status, finished)
            if finished:
                return
            finished = True
            info = dict(details or {})
            info.update(extra)
            normalized = "succeeded" if status in {"succeeded", "passed", "skipped"} else "cancelled" if status == "cancelled" else "failed"
            append("result", "执行完成", status=normalized, result=result, **info)
            logger.info("任务执行结束 schedule_id=%s status=%s", schedule_id, normalized)
            repository.mark_code_review_finished(schedule_id, started, normalized, result)

        params = self.deserialize_param(repository.params(schedule_id))
        logger.debug("run_scheduled.params schedule_id=%s keys=%s", schedule_id, list(params))
        def cancelled():
            return repository.cancellation_requested(schedule_id)
        context = ScheduleContext(run_id=schedule_id, report_progress=report_progress, finish=finish, metadata={"cancel": cancelled})
        try:
            result = self.execute(params, context)
            if not finished:
                finish("succeeded", result)
            logger.info("代码检查执行成功 schedule_id=%s", schedule_id)
            return result
        except Exception as exc:
            if isinstance(exc, ReviewCancelled):
                logger.warning("代码检查已终止 schedule_id=%s", schedule_id)
                append("result", "执行已终止", status="cancelled")
                if not finished:
                    finish("cancelled", {"error": "用户终止"})
                return {"status": "cancelled"}
            error_data = {"type": type(exc).__name__, "message": str(exc)}
            append("result", "执行失败", status="failed", error=error_data)
            logger.exception("代码检查执行失败 schedule_id=%s", schedule_id)
            if not finished:
                finish("failed", {"status": "failed", "error": error_data})
            raise


def sync_schedule() -> None:
    """确保代码检查调度器已注册到通用调度循环。"""
    logger.debug("sync_schedule.begin")
    scheduler = CodeReviewScheduler()
    config = scheduler.display_data()
    repository = ScheduleRepository()
    repository.sync_code_review((scheduler.tool_id, "代码检查", "scheduler", str(TOOL_ROOT / "code_review_scheduler.py"), str(TOOL_ROOT)), (scheduler.schedule_id, scheduler.name, scheduler.tool_id, "daily", scheduler.run_at, "{}", 900, 0, 1, scheduler.next_run_at(), "scheduled", "scheduler", 4))
    # Upgrade historical registrations created before this module moved under
    # the workbench.  Their stale tool entry must never dispatch old code.
    repository.migrate_code_review_entries(str(TOOL_ROOT / "code_review_scheduler.py"), str(TOOL_ROOT))
    logger.info("代码检查调度器已同步 schedule_id=%s", scheduler.schedule_id)
    return config


def task_payload(schedule_id: str | None = None) -> dict[str, Any]:
    """返回任务列表和任务页需要的配置、状态与本次日志。"""
    logger.debug("task_payload.begin schedule_id=%s", schedule_id)
    # 页面每 2 秒轮询一次状态，这条记录属于调试信息，避免正常运行日志刷屏。
    logger.debug("读取代码检查任务参数 schedule_id=%s", schedule_id or CodeReviewScheduler.schedule_id)
    scheduler = CodeReviewScheduler()
    schedule_id = schedule_id or scheduler.schedule_id
    row = None
    try:
        row = ScheduleRepository().get_schedule(schedule_id)
    except Exception:
        logger.exception("读取代码检查任务失败 schedule_id=%s", schedule_id)
        row = None
    db_param = {}
    try:
        db_param = scheduler.deserialize_param(ScheduleRepository().params(schedule_id))
    except Exception:
        logger.exception("读取代码检查任务参数失败 schedule_id=%s", schedule_id)
        pass
    data = scheduler.display_data(db_param)
    raw_error = row["last_error"] if row else None
    try:
        parsed_error = json.loads(raw_error) if isinstance(raw_error, str) and raw_error.strip() else raw_error
    except json.JSONDecodeError:
        parsed_error = {"type": "LegacyError", "message": raw_error}
    data.update({
        "id": schedule_id,
        "name": row["name"] if row else scheduler.name,
        "tool_id": row["tool_id"] if row else scheduler.tool_id,
        "scheduler_type": row["scheduler_type"] if row else scheduler.scheduler_type,
        "run_at": row["run_time"] if row and row["run_time"] else (row["schedule_expr"] if row else scheduler.run_at),
        "last_status": row["last_status"] if row else None,
        "last_error": parsed_error,
        "progress_current": row["progress_current"] if row else 0,
        "progress_total": row["progress_total"] if row else 4,
        "log": read(schedule_id),
    })
    data["last_success"] = last_successful_check(data.get("project_path"), data.get("branch"))
    logger.debug("task_payload.end schedule_id=%s status=%s", schedule_id, data.get("last_status"))
    return data


def task_status_payload(schedule_id: str | None = None) -> dict[str, Any]:
    """仅返回运行状态和执行日志，供页面轮询使用，不读取或重建配置。"""
    schedule_id = schedule_id or CodeReviewScheduler.schedule_id
    row = ScheduleRepository().get_schedule(schedule_id)
    raw_error = row["last_error"] if row else None
    try:
        parsed_error = json.loads(raw_error) if isinstance(raw_error, str) and raw_error.strip() else raw_error
    except json.JSONDecodeError:
        parsed_error = {"type": "LegacyError", "message": raw_error}
    status = {
        "id": schedule_id,
        "last_status": row["last_status"] if row else None,
        "last_error": parsed_error,
        "progress_current": row["progress_current"] if row else 0,
        "progress_total": row["progress_total"] if row else 4,
        "log": read(schedule_id),
    }
    params = CodeReviewScheduler().deserialize_param(row["param_json"]) if row else {}
    status["last_success"] = last_successful_check(params.get("project_path"), params.get("branch"))
    return status


def last_successful_check(project_path: str | None, branch: str | None) -> dict[str, Any] | None:
    """读取最近一次通过检查时持久化的提交和检查时间。"""
    if not project_path or not branch:
        return None
    safe_project = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(project_path).name) or "project"
    safe_branch = re.sub(r"[^A-Za-z0-9._-]+", "-", str(branch)) or "branch"
    state_path = CODE_REVIEW_DATA_ROOT / f"{safe_project}-{safe_branch}" / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    sha = str(state.get("last_successful_sha") or "").strip()
    if not sha:
        return None
    return {
        "sha": sha,
        "commit_message": state.get("last_successful_commit_message") or "",
        "commit_author": state.get("last_successful_commit_author") or "",
        "commit_time": state.get("last_successful_commit_time") or "",
        "checked_at": state.get("checked_at") or "",
    }


def clear_review_history(project_path: str | None, branch: str | None) -> dict[str, Any]:
    """Remove persisted reports and baseline for one project/branch."""
    if not project_path or not branch:
        raise ValueError("请先配置工程路径和 Git 分支")
    safe_project = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(project_path).name) or "project"
    safe_branch = re.sub(r"[^A-Za-z0-9._-]+", "-", str(branch)) or "branch"
    storage_root = CODE_REVIEW_DATA_ROOT / f"{safe_project}-{safe_branch}"
    removed = []
    import shutil
    for name in ("reports", "state.json", "execution-sequence.json"):
        target = storage_root / name
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(name)
        elif target.is_file():
            target.unlink()
            removed.append(name)
    logger.info("代码检查历史已清理 project_path=%s branch=%s removed=%s", project_path, branch, removed)
    return {"project_path": project_path, "branch": branch, "removed": removed}


def update_task_config(project_path: str, branch: str, skill_paths: list[str] | str = ["skills"], allow_extra_rules: bool = False, failure_threshold: str = "high", schedule_id: str | None = None) -> dict[str, Any]:
    logger.debug("update_task_config.begin schedule_id=%s project_path=%s branch=%s", schedule_id, project_path, branch)
    schedule_id = schedule_id or CodeReviewScheduler.schedule_id
    save_param = {"project_path": project_path, "branch": branch, "skill_paths": skill_paths, "allow_extra_rules": allow_extra_rules, "failure_threshold": failure_threshold}
    if not ScheduleRepository().save_params(schedule_id, json.dumps(save_param, ensure_ascii=False)):
        raise ValueError(f"代码检查任务不存在: {schedule_id}")
    logger.info("代码检查配置已保存 schedule_id=%s project_path=%s branch=%s", schedule_id, project_path, branch)
    return task_payload(schedule_id)


def claim_for_start(schedule_id, project_path, branch, skill_paths, allow_extra_rules, failure_threshold):
    from .execution_guard import claim, release
    token = claim(schedule_id, project_path)
    try:
        update_task_config(project_path, branch, skill_paths, allow_extra_rules, failure_threshold, schedule_id)
    except Exception:
        release(token)
        raise
    return token


def start_task(project_path: str, branch: str, skill_paths: list[str] | str = ["skills"], allow_extra_rules: bool = False, failure_threshold: str = "high", schedule_id: str | None = None) -> dict[str, Any]:
    """保存当前配置并在后台执行一次代码检查。"""
    logger.debug("start_task.begin schedule_id=%s project_path=%s branch=%s", schedule_id, project_path, branch)
    schedule_id = schedule_id or CodeReviewScheduler.schedule_id
    from .execution_guard import claim, release
    token = claim_for_start(schedule_id, project_path, branch, skill_paths, allow_extra_rules, failure_threshold)
    def worker():
        try:
            CodeReviewScheduler()._run_claimed(schedule_id)
        except Exception:
            logger.exception("代码检查执行失败 schedule_id=%s", schedule_id)
        finally:
            release(token)
    threading.Thread(target=worker, name=f"review-{schedule_id}", daemon=True).start()
    return task_payload(schedule_id)


def stop_task(schedule_id: str | None = None) -> dict[str, Any]:
    """通过数据库取消指定任务，支持跨进程。"""
    schedule_id = schedule_id or CodeReviewScheduler.schedule_id
    ScheduleRepository().request_running_cancel(schedule_id)
    return task_payload(schedule_id)


def _load_tool_adapter():
    logger.debug("_load_tool_adapter.begin root=%s", TOOL_ROOT)
    path = TOOL_ROOT / "code_review_scheduler.py"
    spec = importlib.util.spec_from_file_location("code_review_tool_scheduler", path)
    if spec is None or spec.loader is None:
        logger.error("无法加载代码检查工具 path=%s", path)
        raise RuntimeError(f"无法加载代码检查承接接口: {path}")
    logger.debug("已加载代码检查工具 path=%s", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
