"""提交本地 Codex 任务并收集 JSONL 执行事件。"""
from __future__ import annotations
import json, os, shutil, subprocess, threading, uuid
from core.storage import connect

class LocalCodexTasks:
    def __init__(self): self._tasks = {}; self._lock = threading.Lock()
    def submit(self, prompt: str, cwd: str, task_id: str | None = None, session_id: str | None = None) -> dict:
        task_id = task_id or uuid.uuid4().hex
        task = {"id": task_id, "prompt": prompt, "cwd": cwd, "session_id": session_id, "status": "running", "events": [], "returncode": None}
        with self._lock: self._tasks[task_id] = task
        threading.Thread(target=self._run, args=(task_id,), daemon=True).start()
        return {"task_id": task_id, "status": "running"}
    def get(self, task_id):
        with self._lock: return self._tasks.get(task_id)
    def _run(self, task_id):
        task = self._tasks[task_id]
        try:
            # Windows 的 PATH 通常只解析 codex.ps1；CreateProcess 无法直接执行
            # PowerShell 脚本，因此优先使用 npm 生成的 codex.cmd 包装器。
            command = "codex.cmd" if os.name == "nt" else "codex"
            executable = shutil.which(command) or shutil.which("codex")
            if not executable:
                raise FileNotFoundError("找不到 codex 命令，请确认 Codex CLI 已安装并在 PATH 中")
            cwd = task["cwd"] if os.path.isdir(task["cwd"]) else os.getcwd()
            # 不把长提示词放入 Windows 命令行参数，避免 WinError 206；Codex
            # 在没有位置参数时从 stdin 接收任务内容。
            if task.get("session_id"):
                # resume 的工作目录由 Popen 的 cwd 决定；该子命令不接受 -C。
                command_args = [executable, "exec", "resume", task["session_id"], "--json", "--skip-git-repo-check", "-"]
            else:
                command_args = [executable, "exec", "--json", "--skip-git-repo-check", "-C", cwd, "-"]
            proc = subprocess.Popen(command_args, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            task["pid"] = proc.pid
            proc.stdin.write(task["prompt"])
            proc.stdin.close()
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    try: event = json.loads(line)
                    except json.JSONDecodeError: event = {"type": "output", "text": line}
                    task["events"].append(event)
            task["returncode"] = proc.wait()
            if not task["events"]:
                task["events"].append({"type": "error", "message": f"Codex 没有返回事件，退出代码：{task['returncode']}"})
            task["status"] = "completed" if task["returncode"] == 0 else "failed"
        except Exception as exc:
            task["status"] = "failed"; task["events"].append({"type": "error", "message": str(exc)})
        finally:
            db = connect()
            try:
                row = db.execute("SELECT messages_json FROM local_codex_tasks WHERE id=?", (task_id,)).fetchone()
                if row:
                    messages = json.loads(row["messages_json"])
                    replies = [e["item"]["text"] for e in task["events"] if isinstance(e.get("item"), dict) and e["item"].get("type") == "agent_message" and e["item"].get("text")]
                    output = "\n\n".join(replies) or "\n".join(e.get("message", "") for e in task["events"] if e.get("message")) or "（无回复，请查看执行记录）"
                    messages.append({"role": "assistant", "content": output})
                    session_id = next((e.get("thread_id") for e in task["events"] if e.get("thread_id")), task.get("session_id"))
                    db.execute("UPDATE local_codex_tasks SET status=?, session_id=COALESCE(?,session_id), messages_json=?, log=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (task["status"], session_id, json.dumps(messages, ensure_ascii=False), json.dumps(task["events"], ensure_ascii=False), task_id))
                    db.commit()
            finally:
                db.close()

tasks = LocalCodexTasks()
