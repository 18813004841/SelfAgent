"""使用独立进程验证 SQLite Repository 并发写入，无正式数据访问。"""
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
import multiprocessing
from pathlib import Path
import sys
import tempfile

SRC = Path(__file__).resolve().parents[1] / "workbench/machine-dashboard-server/src"
sys.path.insert(0, str(SRC))


def write_batch(database, batch):
    from core import storage
    from core.repositories import ScheduleRepository
    storage.DB_PATH = Path(database)
    repository = ScheduleRepository()
    for index in range(20):
        repository.create({
            "id": f"{batch}-{index}", "name": "concurrent", "tool_id": "tool",
            "schedule_type": "interval", "schedule_expr": "60", "args_json": "{}",
            "timeout": 30, "retry": 0, "enabled": 0, "next_run": 0,
            "task_type": "scheduled", "dispatcher": "scheduler", "progress_total": 1,
            "scheduler_type": None, "run_type": 1, "run_time": None, "param_json": "{}",
        })
    return batch


def main():
    from core import storage
    from core.repositories import ScheduleRepository
    with tempfile.TemporaryDirectory(prefix="selfagent-concurrency-") as temp:
        storage.DB_PATH = Path(temp) / "test.db"
        storage.USER_ROOT = Path(temp) / "LocalWorkbench"
        repository = ScheduleRepository()
        repository.upsert_tool(("tool", "concurrent", "scheduler", "entry", temp, 1))
        with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
            jobs = [pool.submit(write_batch, str(storage.DB_PATH), batch) for batch in range(4)]
            assert sorted(job.result(timeout=45) for job in jobs) == list(range(4))
        rows = repository.list_all()
        assert len(rows) == 80 and len({row["id"] for row in rows}) == 80
        with closing(storage.connect()) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("SQLite concurrency passed: 4 processes, 80 committed schedules, integrity ok")


if __name__ == "__main__":
    main()
