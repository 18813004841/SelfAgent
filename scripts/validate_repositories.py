"""在隔离 SQLite 中验证任务 Repository 的实际读写接口。"""
import json
import sys
import tempfile
from pathlib import Path
import time
import sqlite3
from contextlib import closing

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workbench/machine-dashboard-server/src"))


def main():
    from core import storage
    from core.repositories import LocalCodexTaskRepository, ScheduleRepository
    with tempfile.TemporaryDirectory(prefix="selfagent-repositories-") as root:
        storage.USER_ROOT = Path(root)
        storage.DB_PATH = Path(root) / "data/test.db"
        tasks = LocalCodexTaskRepository()
        tasks.create("test", "测试", root)
        tasks.mark_running("test", root, "prompt", [{"role": "user", "content": "测试"}])
        tasks.save_result("test", "completed", "session", [], "output")
        assert tasks.get("test")["session_id"] == "session"
        tasks.update("test", cwd=root, status="idle", prompt="", messages=[], log="", skill_paths=[], allow_extra_rules=False)
        assert len(tasks.list()) == 1
        assert tasks.delete("test")
        assert tasks.get("test") is None
        schedules = ScheduleRepository()
        schedules.upsert_tool(("schedule", "测试", "scheduler", "entry", root, 1))
        values = {"id": "schedule", "name": "测试调度", "tool_id": "schedule", "schedule_type": "once", "schedule_expr": "00:00", "args_json": "{}", "timeout": 30, "retry": 0, "enabled": 1, "next_run": time.time() - 1, "task_type": "scheduled", "dispatcher": "scheduler", "progress_total": 1, "scheduler_type": "test_scheduler", "run_type": 2, "run_time": "00:00", "param_json": "{}"}
        schedules.create(values)
        with closing(storage.connect()) as db:
            assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
            assert db.execute("PRAGMA busy_timeout").fetchone()[0] >= 10000
        original = schedules.get("schedule")["param_json"]
        try:
            schedules.update("missing", {"param_json": "{\"bad\": true}"})
        except sqlite3.Error:
            pass
        assert schedules.get("schedule")["param_json"] == original
        missing = {**values, "id": "missing-tool-schedule", "tool_id": "absent"}
        try:
            schedules.create(missing)
        except ValueError:
            pass
        else:
            raise AssertionError("missing tool accepted")
        assert schedules.get("missing-tool-schedule") is None
        # 失败的写事务不能保留锁，下一连接应能立即提交。
        schedules.create({**values, "id": "after-failure"})
        assert schedules.delete("after-failure")
        # 第二条 SQL 已执行到数据库、但被约束拒绝时，第一条工具注册必须一并回滚。
        # 触发器让故障发生在 INSERT 之后，避免只验证参数绑定失败。
        with closing(storage.connect()) as db:
            db.execute("CREATE TRIGGER fail_schedule_insert AFTER INSERT ON schedules BEGIN SELECT RAISE(ABORT, 'injected transaction failure'); END")
            db.commit()
        invalid = ("rollback-schedule", "rollback", "rollback-tool", "daily", "00:00", "{}", 30, 0, 1, 0, "scheduled", "scheduler", 1)
        try:
            schedules.sync_code_review(("rollback-tool", "rollback", "scheduler", "entry", root), invalid)
        except sqlite3.DatabaseError:
            pass
        else:
            raise AssertionError("invalid schedule unexpectedly committed")
        with closing(storage.connect()) as db:
            db.execute("DROP TRIGGER fail_schedule_insert")
            db.commit()
        assert all(row["tool_id"] != "rollback-tool" for row in schedules.list_tools())
        assert schedules.due_ids(time.time()) == ["schedule"]
        assert schedules.update("schedule", {"name": "已更新", "enabled": 1, "param_json": json.dumps({"x": 1})})
        assert schedules.get("schedule")["name"] == "已更新"
        assert schedules.request_cancel("schedule")
        assert schedules.get("schedule")["cancel_requested"] == 1
        schedules.disable("schedule")
        assert schedules.get("schedule")["enabled"] == 0
        assert schedules.delete("schedule")
        schedules.create(values)
        from schedulers.execution_guard import ReviewExecutionRepository
        guard = ReviewExecutionRepository()
        token = guard.claim("schedule", root, process_alive=lambda pid: True)
        assert token
        guard.release(token)
    print("repository CRUD validation passed")


if __name__ == "__main__":
    main()
