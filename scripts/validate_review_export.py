"""Validate the real review export route using isolated in-memory fixtures."""
import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench/machine-dashboard-server/src"))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        os.environ.update(LOCALAPPDATA=tmp, WORKBENCH_OUTPUT_DIR=str(base / "output"), WORKBENCH_LOG_PATH=str(base / "logs"), LOCAL_WORKBENCH_START_TIMESTAMP="review-export-test")
        from view import router
        from view.router import ViewContext
        import view.code_review_view
        import schedulers.code_review_scheduler as scheduler

        class Request:
            path = "/api/scheduler-tasks/code-review/export"
            def __init__(self): self.wfile = io.BytesIO(); self.headers = {}; self.status = None
            def send_response(self, status): self.status = status
            def send_header(self, key, value): self.headers[key] = value
            def end_headers(self): pass

        artifacts = base / "review-data" / "project-main" / "reports" / "project-main-0001"
        artifacts.mkdir(parents=True)
        report = artifacts / "result.json"
        report.write_text('{"检查结果":"检查完成"}', encoding="utf-8")
        (artifacts / "changes.diff").write_text("example diff", encoding="utf-8")
        (artifacts / "codex-input-001.md").write_text("prompt", encoding="utf-8")
        (artifacts / "codex-output-001.txt").write_text("output", encoding="utf-8")
        (artifacts / "review-manifest.json").write_text("{}", encoding="utf-8")
        row = {"scheduler_type": "code_review_scheduler", "last_status": "succeeded", "name": "测试任务"}
        run = {"id": 1, "status": "succeeded", "started_at": 1, "finished_at": 2, "output": json.dumps({"导出报告": str(report)})}
        req = Request()
        with patch.object(scheduler, "CODE_REVIEW_DATA_ROOT", base / "review-data"), patch.object(scheduler.ScheduleRepository, "schedule_detail", return_value=(row, [run])), patch.object(scheduler, "read", return_value={"events": [{"message": "测试日志"}]}):
            router.dispatch(ViewContext(req, req.path, {"schedule_id": "task1"}, "POST", None))
            assert req.status == 200 and req.headers["Content-Type"] == "application/zip"
            with zipfile.ZipFile(io.BytesIO(req.wfile.getvalue())) as archive:
                names = set(archive.namelist())
                assert {"执行信息.json", "执行日志.json", "审查记录/result.json", "审查记录/changes.diff", "审查记录/review-manifest.json", "审查记录/codex-input-001.md", "审查记录/codex-output-001.txt"} <= names
                assert json.loads(archive.read("执行信息.json"))["任务名"] == "测试任务"
            with patch.object(scheduler.ScheduleRepository, "schedule_detail", return_value=(dict(row, last_status="running"), [run])):
                try: scheduler.export_last_review("task1")
                except ValueError: pass
                else: raise AssertionError("running task was exported")
            with patch.object(scheduler.ScheduleRepository, "schedule_detail", return_value=(row, [])):
                try: scheduler.export_last_review("task1")
                except ValueError: pass
                else: raise AssertionError("missing run was exported")
        import logging
        logging.shutdown()
        print("PASS: export route, ZIP contents, running and empty cases")


if __name__ == "__main__": main()
