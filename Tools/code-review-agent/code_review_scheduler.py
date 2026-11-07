"""代码检查工具承接 code_review_scheduler 的统一接口。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from code_review.config import ReviewConfig
from code_review.pipeline import ReviewPipeline


class ReviewCancelled(RuntimeError):
    pass


def execute(args: Mapping[str, Any], context: Any) -> dict[str, Any]:
    """接收调度器传入的工程地址和 Git 分支并执行检查。"""
    project_path = str(args.get("project_path", "") or "").strip()
    branch = str(args.get("branch", "") or "").strip()
    context.progress(2, 4, "已接收调度参数", project_path=project_path, branch=branch)
    if not project_path or not branch:
        result = {"status": "failed", "error": "工程地址或 Git 分支未配置", "project_path": project_path, "branch": branch}
        context.complete("failed", result)
        return result
    project = Path(project_path).expanduser().resolve()
    if not project.is_dir():
        result = {"status": "failed", "error": "工程目录不存在", "project_path": str(project), "branch": branch}
        context.complete("failed", result)
        return result

    context.progress(3, 4, "开始检查工程", project_path=str(project), branch=branch)
    try:
        config = ReviewConfig.load(ROOT / "config.example.json")
        config.raw["project"]["path"] = str(project)
        config.raw["project"]["branch"] = branch
        if "skill_paths" in args:
            config.raw.setdefault("checks", {})["skill_paths"] = args["skill_paths"]
        config.raw.setdefault("checks", {})["allow_extra_rules"] = bool(args.get("allow_extra_rules"))
        config.raw.setdefault("checks", {})["failure_threshold"] = str(args.get("failure_threshold", "high"))
        def cancelled() -> bool:
            check = args.get("cancel")
            return bool(check()) if callable(check) else False

        review = ReviewPipeline(
            config,
            progress=lambda **event: context.progress(event.get("current", 0), event.get("total", 10), event.get("message", ""), **{k: v for k, v in event.items() if k not in {"current", "total", "message"}}),
            cancel=cancelled,
        ).run()
    except RuntimeError as exc:
        if "已终止" not in str(exc):
            raise
        result = {"status": "cancelled", "project_path": str(project), "branch": branch}
        context.complete("cancelled", result)
        return result
    except FileNotFoundError as exc:
        missing = exc.filename or "未知路径"
        result = {"status": "failed", "error": f"找不到文件或命令: {missing}", "project_path": str(project), "branch": branch}
        context.complete("failed", result)
        return result
    result = review.as_display_dict()
    status = "succeeded" if review.status in {"passed", "skipped"} else "failed"
    context.progress(4, 4, "检查执行结束", status=review.status)
    context.complete(status, result)
    return result


def main() -> int:
    """保留命令行入口，便于单独验证承接参数。"""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="{}")
    options = json.loads(parser.parse_args().input)
    events: list[dict[str, Any]] = []

    class DirectContext:
        def progress(self, current: int, total: int | None = None, message: str = "", **details: Any) -> None:
            events.append({"kind": "progress", "current": current, "total": total, "message": message, "details": details})

        def complete(self, status: str = "succeeded", result: Any = None, **details: Any) -> None:
            events.append({"kind": "result", "status": status, "result": result, "details": details})

    result = execute(options, DirectContext())
    print(json.dumps({"events": events, "result": result}, ensure_ascii=False))
    return 0 if result.get("status") in {"passed", "skipped", "succeeded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
