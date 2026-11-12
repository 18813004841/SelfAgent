"""跨进程执行名额：同一任务、同一工程禁止并行。"""
import os
import uuid
from pathlib import Path
from core.storage import connect


def claim(schedule_id, project_path=None):
    import json
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS review_execution (token TEXT PRIMARY KEY, task_id TEXT UNIQUE, project TEXT UNIQUE, pid INTEGER)")
        db.execute("BEGIN IMMEDIATE")
        for old_token, pid in db.execute("SELECT token,pid FROM review_execution").fetchall():
            if not process_alive(pid):
                db.execute("DELETE FROM review_execution WHERE token=?", (old_token,))
        row = db.execute("SELECT param_json FROM schedules WHERE id=?", (schedule_id,)).fetchone()
        if not row:
            raise ValueError("任务不存在")
        params = json.loads(row[0] or '{}')
        if project_path is not None:
            params['project_path'] = project_path
        if not params.get('project_path'):
            raise ValueError("请先配置工程路径")
        project = os.path.normcase(str(Path(params['project_path']).expanduser().resolve()))
        if db.execute("SELECT 1 FROM review_execution WHERE task_id=? OR project=?", (schedule_id, project)).fetchone():
            raise RuntimeError("任务或工程正在检查，请等待完成后重试")
        limit = max(1, int(os.environ.get('CODE_REVIEW_MAX_CONCURRENCY', '3')))
        if db.execute("SELECT COUNT(*) FROM review_execution").fetchone()[0] >= limit:
            raise RuntimeError("已达到代码检查并发上限，请稍后重试")
        token = uuid.uuid4().hex
        db.execute("INSERT INTO review_execution VALUES(?,?,?,?)", (token, schedule_id, project, os.getpid()))
    return token


def release(token):
    with connect() as db:
        db.execute("DELETE FROM review_execution WHERE token=?", (token,))


def process_alive(pid):
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.windll.kernel32.GetLastError() == 5
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
