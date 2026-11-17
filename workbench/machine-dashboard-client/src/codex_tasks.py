from __future__ import annotations
import json, os, shutil, sqlite3, subprocess, threading, time, uuid
from pathlib import Path
from contextlib import contextmanager

class CodexTaskStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._running = {}
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, name TEXT, cwd TEXT, status TEXT, prompt TEXT, messages_json TEXT, session_id TEXT, skill_paths_json TEXT, allow_extra_rules INTEGER, log TEXT)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def list(self):
        with self._connect() as db:
            rows = db.execute("SELECT * FROM tasks ORDER BY rowid DESC").fetchall()
        return [self._public(row) for row in rows]

    def get(self, task_id: str):
        with self._connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._public(row) if row else None

    def create(self, name: str, cwd: str):
        task_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)", (task_id, name, cwd, "idle", "", "[]", None, "[]", 1, ""))
        return {"id": task_id, "name": name, "cwd": cwd, "status": "idle", "messages": []}

    def delete(self, task_id: str):
        with self._connect() as db:
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))

    def update(self, body: dict):
        current = self.get(str(body.get("id", "")))
        if not current:
            raise ValueError("任务不存在")
        messages = body.get("messages", current["messages"])
        skills = body.get("skill_paths", current["skill_paths"])
        with self._connect() as db:
            db.execute("UPDATE tasks SET cwd=?, status=?, prompt=?, messages_json=?, skill_paths_json=?, allow_extra_rules=?, log=? WHERE id=?", (str(body.get("cwd", current["cwd"])), str(body.get("status", current["status"])), str(body.get("prompt", current["prompt"])), json.dumps(messages, ensure_ascii=False), json.dumps(skills, ensure_ascii=False), int(bool(body.get("allow_extra_rules", current["allow_extra_rules"]))), str(body.get("log", current["log"])), current["id"]))

    def mark_running(self, task_id, cwd, prompt):
        current = self.get(task_id)
        messages = current["messages"] + [{"role": "user", "content": prompt}]
        self.update({"id": task_id, "cwd": cwd, "status": "running", "prompt": prompt, "messages": messages})

    def submit(self, prompt, cwd, task_id, session_id, timeout_seconds=None):
        if timeout_seconds is not None and (type(timeout_seconds) is not int or timeout_seconds < 1 or timeout_seconds > 86400):
            raise ValueError("timeout_seconds 必须是 1 到 86400 的整数")
        task = {"id": task_id, "prompt": prompt, "cwd": cwd, "session_id": session_id, "status": "running", "events": [], "returncode": None, "timeout": timeout_seconds, "cancel": False, "process": None}
        with self._lock:
            if self._running.get(task_id, {}).get("status") == "running":
                raise ValueError("任务正在执行，请先取消或等待完成")
            self.mark_running(task_id, cwd, prompt)
            self._running[task_id] = task
        threading.Thread(target=self._run, args=(task_id,), daemon=True).start()
        return {"task_id": task_id, "status": "running"}

    def cancel(self, task_id):
        with self._lock:
            task = self._running.get(task_id)
            if not task:
                raise ValueError("没有正在执行的任务")
            if task["status"] != "running":
                return {"task_id": task_id, "status": task["status"]}
            task["cancel"] = True
        return {"task_id": task_id, "status": "cancelling"}

    def running(self, task_id):
        with self._lock:
            return self._running.get(task_id)

    def save_result(self, task):
        current = self.get(task["id"])
        if not current:
            return
        replies = [event["item"]["text"] for event in task["events"] if isinstance(event.get("item"), dict) and event["item"].get("type") == "agent_message" and event["item"].get("text")]
        output = "\n\n".join(replies) or "\n".join(event.get("message", "") for event in task["events"] if event.get("message")) or "（无回复，请查看执行记录）"
        messages = current["messages"]
        if not messages or messages[-1].get("role") != "assistant":
            messages.append({"role": "assistant", "content": output})
        else:
            messages[-1]["content"] = output
        session_id = next((event.get("thread_id") for event in task["events"] if event.get("thread_id")), task.get("session_id"))
        with self._connect() as db:
            db.execute("UPDATE tasks SET status=?, session_id=?, messages_json=?, log=? WHERE id=?", (task["status"], session_id, json.dumps(messages, ensure_ascii=False), json.dumps(task["events"], ensure_ascii=False), task["id"]))

    def _run(self, task_id):
        task = self._running[task_id]
        try:
            command = "codex.cmd" if os.name == "nt" else "codex"
            executable = shutil.which(command) or shutil.which("codex")
            if not executable and not os.environ.get("WORKBENCH_LOCAL_CODEX_ARGV"):
                raise FileNotFoundError("找不到 codex 命令，请确认 Codex CLI 已安装并在 PATH 中")
            cwd = task["cwd"] if os.path.isdir(task["cwd"]) else os.getcwd()
            override = os.environ.get("WORKBENCH_LOCAL_CODEX_ARGV")
            if override:
                args = json.loads(override)
                if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
                    raise ValueError("WORKBENCH_LOCAL_CODEX_ARGV 必须是字符串数组")
            elif task.get("session_id"):
                args = [executable, "exec", "resume", task["session_id"], "--json", "--skip-git-repo-check", "-"]
            else:
                args = [executable, "exec", "--json", "--skip-git-repo-check", "-C", cwd, "-"]
            proc = subprocess.Popen(args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            task["process"] = proc
            task["pid"] = proc.pid
            proc.stdin.write(task["prompt"])
            proc.stdin.close()
            def read_output():
                for line in proc.stdout:
                    line = line.rstrip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        event = {"type": "output", "text": line}
                    task["events"].append(event)
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            outcome = None
            deadline = time.monotonic() + task["timeout"] if task.get("timeout") else None
            while proc.poll() is None:
                if task.get("cancel"):
                    proc.terminate()
                    outcome = "cancelled"
                    break
                if deadline and time.monotonic() >= deadline:
                    proc.terminate()
                    outcome = "timed_out"
                    break
                time.sleep(0.05)
            else:
                outcome = "cancelled" if task.get("cancel") else ("completed" if proc.returncode == 0 else "failed")
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            reader.join(timeout=5)
            task["returncode"] = proc.returncode
            task["status"] = outcome
            self.save_result(task)
        except Exception as exc:
            task["status"] = "failed"
            task["events"].append({"type": "error", "message": str(exc)})
            self.save_result(task)

    @staticmethod
    def _public(row):
        return {"id": row["id"], "name": row["name"], "cwd": row["cwd"], "status": row["status"], "prompt": row["prompt"], "messages": json.loads(row["messages_json"] or "[]"), "session_id": row["session_id"], "skill_paths": json.loads(row["skill_paths_json"] or "[]"), "allow_extra_rules": bool(row["allow_extra_rules"]), "log": row["log"]}
