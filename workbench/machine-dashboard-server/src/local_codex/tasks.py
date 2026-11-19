"""提交本地 Codex 任务并收集 JSONL 执行事件。"""
from __future__ import annotations
import json, os, threading, uuid
from integrations.codex_cli import CodexCliClient, CodexCliError
from core.repositories import LocalCodexTaskRepository

class LocalCodexTasks:
    def __init__(self): self._tasks = {}; self._lock = threading.Lock(); self._repository = LocalCodexTaskRepository()
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
            cwd = task["cwd"] if os.path.isdir(task["cwd"]) else os.getcwd()
            def on_event(event): task["events"].append(event)
            result = CodexCliClient(timeout=900).execute(task["prompt"], cwd=cwd,
                session_id=task.get("session_id"), on_event=on_event)
            task["pid"] = result.pid
            task["returncode"] = result.returncode
            if not task["events"]:
                task["events"].append({"type": "error", "message": f"Codex 没有返回事件，退出代码：{task['returncode']}"})
            task["status"] = "completed" if task["returncode"] == 0 else "failed"
        except Exception as exc:
            task["status"] = "failed"; task["events"].append({"type": "error", "message": str(exc)})
        finally:
            row = self._repository.get_fields(task_id, "messages_json")
            if row:
                    messages = json.loads(row["messages_json"])
                    replies = [e["item"]["text"] for e in task["events"] if isinstance(e.get("item"), dict) and e["item"].get("type") == "agent_message" and e["item"].get("text")]
                    output = "\n\n".join(replies) or "\n".join(e.get("message", "") for e in task["events"] if e.get("message")) or "（无回复，请查看执行记录）"
                    messages.append({"role": "assistant", "content": output})
                    session_id = next((e.get("thread_id") for e in task["events"] if e.get("thread_id")), task.get("session_id"))
                    self._repository.save_result(task_id, task["status"], session_id, messages, json.dumps(task["events"], ensure_ascii=False))

tasks = LocalCodexTasks()
