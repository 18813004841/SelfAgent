"""工作台持久化 Repository。

Repository 只负责数据库连接和 SQL，不承载 HTTP、调度或进程业务。新增查询
应优先放在这里，以便统一事务边界和后续迁移。
"""
import json
import os
import uuid
from pathlib import Path
from contextlib import closing
from .storage import connect


class LocalCodexTaskRepository:
    """本地 Codex 任务的读写边界。每个写操作使用一个短事务。"""

    def list(self):
        with closing(connect()) as db:
            return db.execute(
                "SELECT * FROM local_codex_tasks ORDER BY updated_at DESC"
            ).fetchall()

    def get(self, task_id):
        with closing(connect()) as db:
            return db.execute(
                "SELECT * FROM local_codex_tasks WHERE id=?", (task_id,)
            ).fetchone()

    def get_fields(self, task_id, fields="skill_paths_json, allow_extra_rules"):
        allowed = {"skill_paths_json", "allow_extra_rules", "messages_json", "session_id"}
        selected = [item.strip() for item in fields.split(",")]
        if not selected or any(item not in allowed for item in selected):
            raise ValueError("invalid repository field")
        with closing(connect()) as db:
            return db.execute(
                f"SELECT {', '.join(selected)} FROM local_codex_tasks WHERE id=?",
                (task_id,),
            ).fetchone()

    def create(self, task_id, name, cwd):
        with closing(connect()) as db:
            db.execute(
                "INSERT INTO local_codex_tasks(id,name,cwd) VALUES(?,?,?)",
                (task_id, name, cwd),
            )
            db.commit()

    def delete(self, task_id):
        with closing(connect()) as db:
            db.execute("DELETE FROM local_codex_tasks WHERE id=?", (task_id,))
            changed = db.total_changes
            db.commit()
            return changed > 0

    def update(self, task_id, *, cwd, status, prompt, messages, log,
               skill_paths, allow_extra_rules):
        with closing(connect()) as db:
            db.execute(
                "UPDATE local_codex_tasks SET cwd=?, status=?, prompt=?, "
                "messages_json=?, log=?, skill_paths_json=?, allow_extra_rules=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (cwd, status, prompt, json.dumps(messages, ensure_ascii=False), log,
                 json.dumps(skill_paths, ensure_ascii=False), int(bool(allow_extra_rules)),
                 task_id),
            )
            db.commit()

    def mark_running(self, task_id, cwd, prompt, messages):
        with closing(connect()) as db:
            db.execute(
                "UPDATE local_codex_tasks SET status='running', cwd=?, prompt=?, "
                "messages_json=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (cwd, prompt, json.dumps(messages, ensure_ascii=False), task_id),
            )
            db.commit()

    def save_result(self, task_id, status, session_id, messages, log):
        with closing(connect()) as db:
            db.execute(
                "UPDATE local_codex_tasks SET status=?, session_id=COALESCE(?, session_id), "
                "messages_json=?, log=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, session_id, json.dumps(messages, ensure_ascii=False), log, task_id),
            )
            db.commit()


class ScheduleRepository:
    """调度主循环使用的任务读取和状态更新。"""

    def due_ids(self, now: float):
        with closing(connect()) as db:
            return [row["id"] for row in db.execute(
                "SELECT id FROM schedules WHERE enabled=1 AND (next_run IS NULL OR next_run<=?)",
                (now,),
            ).fetchall()]

    def get(self, schedule_id):
        with closing(connect()) as db:
            return db.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()

    def set_next_run(self, schedule_id, next_run):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET next_run=? WHERE id=?", (next_run, schedule_id))
            db.commit()

    def disable(self, schedule_id):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET enabled=0,next_run=NULL WHERE id=?", (schedule_id,))
            db.commit()

    def list_all(self):
        with closing(connect()) as db:
            return db.execute("SELECT * FROM schedules ORDER BY name").fetchall()

    def create(self, values):
        columns = ("id", "name", "tool_id", "schedule_type", "schedule_expr", "args_json", "timeout", "retry", "enabled", "next_run", "task_type", "dispatcher", "progress_total", "scheduler_type", "run_type", "run_time", "param_json")
        with closing(connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM tools WHERE tool_id=?", (values["tool_id"],)).fetchone() is None:
                raise ValueError("tool not found")
            db.execute(f"INSERT INTO schedules({','.join(columns)}) VALUES({','.join('?' for _ in columns)})", tuple(values[column] for column in columns))
            return values["id"]

    def update(self, schedule_id, fields):
        allowed = {key: value for key, value in fields.items() if key in {"name", "enabled", "run_type", "run_time", "param_json"}}
        if not allowed:
            return False
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET " + ",".join(f"{key}=?" for key in allowed) + " WHERE id=?", (*allowed.values(), schedule_id))
            changed = db.total_changes
            db.commit()
            return changed > 0

    def delete(self, schedule_id):
        with closing(connect()) as db:
            db.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
            changed = db.total_changes
            db.commit()
            return changed > 0

    def request_cancel(self, schedule_id):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET cancel_requested=1,last_status='cancelling' WHERE id=?", (schedule_id,))
            changed = db.total_changes
            db.commit()
            return changed > 0

    def mark_running(self, schedule_id, started, total):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET last_run=?,last_status='running',progress_current=0,progress_total=? WHERE id=?", (started, total, schedule_id))
            db.commit()

    def progress(self, schedule_id, current, total):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET progress_current=?,progress_total=? WHERE id=?", (current, total, schedule_id))
            db.commit()

    def record_run(self, schedule_id, started, status, output):
        with closing(connect()) as db:
            db.execute("INSERT INTO runs(schedule_id,started_at,finished_at,status,output) VALUES(?,?,?,?,?)", (schedule_id, started, __import__('time').time(), status, output))
            db.execute("UPDATE schedules SET last_run=?,last_status=? WHERE id=?", (started, status, schedule_id))
            db.commit()

    def mark_code_review_running(self, schedule_id, started):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET last_run=?,last_status='running',last_error=NULL,progress_current=0,progress_total=4,cancel_requested=0 WHERE id=?", (started, schedule_id))
            db.commit()

    def mark_code_review_progress(self, schedule_id, current, total=None):
        with closing(connect()) as db:
            if total:
                db.execute("UPDATE schedules SET progress_current=?,progress_total=? WHERE id=?", (current, total, schedule_id))
            else:
                db.execute("UPDATE schedules SET progress_current=? WHERE id=?", (current, schedule_id))
            db.commit()

    def mark_code_review_finished(self, schedule_id, started, status, result):
        with closing(connect()) as db:
            import json
            output = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2, default=str)
            error = None if status == "succeeded" else json.dumps(result, ensure_ascii=False, indent=2, default=str)
            db.execute("INSERT INTO runs(schedule_id,started_at,finished_at,status,output,error) VALUES(?,?,?,?,?,?)", (schedule_id, started, __import__('time').time(), status, output, error))
            db.execute("UPDATE schedules SET last_status=?,progress_current=progress_total,last_error=? WHERE id=?", (status, error, schedule_id))
            db.commit()

    def cancellation_requested(self, schedule_id):
        with closing(connect()) as db:
            row = db.execute("SELECT cancel_requested FROM schedules WHERE id=?", (schedule_id,)).fetchone()
            return bool(row and row[0])

    def params(self, schedule_id):
        with closing(connect()) as db:
            row = db.execute("SELECT param_json FROM schedules WHERE id=?", (schedule_id,)).fetchone()
            return row[0] if row else "{}"

    def sync_code_review(self, tool_values, schedule_values):
        with closing(connect()) as db:
            db.execute("INSERT OR REPLACE INTO tools(tool_id,name,type,entry,workdir,enabled) VALUES(?,?,?,?,?,1)", tool_values)
            db.execute("INSERT INTO schedules(id,name,tool_id,schedule_type,schedule_expr,args_json,timeout,retry,enabled,next_run,task_type,dispatcher,progress_total) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,tool_id=excluded.tool_id,schedule_type=excluded.schedule_type,schedule_expr=excluded.schedule_expr,args_json=excluded.args_json", schedule_values)
            db.commit()

    def migrate_code_review_entries(self, entry: str, workdir: str) -> int:
        """Point legacy code-review registrations at the current implementation."""
        with closing(connect()) as db:
            db.execute("UPDATE tools SET entry=?,workdir=? WHERE tool_id=?", (entry, workdir, "code-review-agent"))
            cur = db.execute(
                "UPDATE schedules SET scheduler_type='code_review_scheduler' "
                "WHERE tool_id='code-review-agent'"
            )
            db.commit()
            return cur.rowcount

    def get_schedule(self, schedule_id):
        with closing(connect()) as db:
            return db.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()

    def save_params(self, schedule_id, params_json):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET param_json=? WHERE id=?", (params_json, schedule_id))
            db.commit()
            return db.total_changes > 0

    def request_running_cancel(self, schedule_id):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET cancel_requested=1,last_status='cancelling' WHERE id=? AND last_status='running'", (schedule_id,))
            changed = db.total_changes
            db.commit()
            return changed > 0

    def upsert_tool(self, values):
        with closing(connect()) as db:
            db.execute("INSERT OR REPLACE INTO tools(tool_id,name,type,entry,workdir,enabled) VALUES(?,?,?,?,?,?)", values)
            db.commit()

    def replace_schedule(self, values):
        with closing(connect()) as db:
            db.execute("INSERT OR REPLACE INTO schedules(id,name,tool_id,schedule_type,schedule_expr,args_json,timeout,retry,enabled,next_run,task_type,dispatcher,progress_total) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
            db.commit()

    def set_enabled(self, schedule_id, enabled):
        with closing(connect()) as db:
            db.execute("UPDATE schedules SET enabled=? WHERE id=?", (enabled, schedule_id))
            db.commit()

    def list_tools(self):
        with closing(connect()) as db:
            return db.execute("SELECT * FROM tools ORDER BY name").fetchall()

    def schedule_detail(self, schedule_id):
        with closing(connect()) as db:
            row = db.execute("SELECT s.*, t.name tool_name, t.type tool_type FROM schedules s LEFT JOIN tools t ON t.tool_id=s.tool_id WHERE s.id=?", (schedule_id,)).fetchone()
            runs = db.execute("SELECT * FROM runs WHERE schedule_id=? ORDER BY id DESC LIMIT 30", (schedule_id,)).fetchall()
            return row, runs



class ReviewExecutionRepository:
    """原子执行名额；进程存活判断由调用层注入。"""

    def claim(self, schedule_id, project_path=None, *, process_alive):
        import json
        with closing(connect()) as db, db:
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


    def release(self, token):
        with closing(connect()) as db, db:
            db.execute("DELETE FROM review_execution WHERE token=?", (token,))

