"""服务器端 Codex 维护会话与工作台重启接口。"""
import json, os, subprocess, sys, threading, time, uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from integrations.codex_cli import CodexCliClient
from core.storage import connect
from . import router
from .logging import get_logger

logger = get_logger("server_maintenance", Path(__file__).resolve().parents[2] / "src/core/logs")
WORKSPACE = Path(__file__).resolve().parents[2]
_lock = threading.Lock(); _tasks = {}; _restart_pending = False

def _session():
    with connect() as db:
        row = db.execute("SELECT * FROM server_maintenance_session WHERE id=1").fetchone()
        if not row:
            db.execute("INSERT INTO server_maintenance_session(id) VALUES(1)"); db.commit()
            return {"session_id": None, "messages": [], "status": "idle"}
        return {"session_id": row["session_id"], "messages": json.loads(row["messages_json"] or "[]"), "status": row["status"]}

def _save(session_id, messages, status):
    with connect() as db:
        db.execute("UPDATE server_maintenance_session SET session_id=?, messages_json=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", (session_id, json.dumps(messages, ensure_ascii=False), status)); db.commit()

def _run(task_id, message, session_id, messages):
    task = _tasks[task_id]
    try:
        result = CodexCliClient(timeout=900, sandbox="workspace-write").execute(message, cwd=WORKSPACE, session_id=session_id, cancel=lambda: task.get("cancelled", False), on_event=lambda e: task["events"].append(e))
        reply = result.text or "（Codex 未返回文本回复）"; new_session = next((e.get("thread_id") for e in task["events"] if e.get("thread_id")), session_id)
        messages.append({"role":"assistant", "content":reply}); _save(new_session, messages, "completed"); task.update(status="completed", messages=messages, session_id=new_session)
    except Exception as exc:
        task.update(status="cancelled" if task.get("cancelled") else "failed", error=str(exc), messages=messages); _save(session_id, messages, task["status"])

@router.route("GET", "/api/server-maintenance/session", "/api/server-maintenance/task")
@router.route("POST", "/api/server-maintenance/chat", "/api/server-maintenance/cancel", "/api/server-maintenance/restart")
def handle(ctx):
    global _restart_pending
    if ctx.path.endswith("/session"):
        data=_session(); ctx.request.send_json(200, {"ok":True, "workspace":str(WORKSPACE), **data}); return True
    if ctx.path.endswith("/task"):
        tid=parse_qs(urlparse(ctx.request.path).query).get("task_id", [""])[0]; task=_tasks.get(tid)
        if not task: ctx.request.send_json(404, {"ok":False,"error":"任务不存在"})
        else: ctx.request.send_json(200, {"ok":True,"task":task})
        return True
    if ctx.path.endswith("/chat"):
        message=ctx.body.get("message")
        if not isinstance(message, str) or not message.strip(): raise ValueError("message 不能为空")
        with _lock:
            if any(t.get("status")=="running" for t in _tasks.values()): raise RuntimeError("已有 Codex 任务正在执行")
            s=_session(); messages=s["messages"] + [{"role":"user","content":message.strip()}]; tid=uuid.uuid4().hex
            task={"task_id":tid,"status":"running","events":[],"messages":messages}; _tasks[tid]=task; _save(s["session_id"], messages, "running")
            threading.Thread(target=_run,args=(tid,message.strip(),s["session_id"],messages),daemon=True).start()
        ctx.request.send_json(202,{"ok":True,"task_id":tid,"status":"running"}); return True
    if ctx.path.endswith("/cancel"):
        running=next((t for t in _tasks.values() if t.get("status")=="running"),None)
        if not running: raise RuntimeError("没有正在执行的任务")
        running["cancelled"]=True; ctx.request.send_json(200,{"ok":True}); return True
    if ctx.path.endswith("/restart"):
        if _restart_pending: raise RuntimeError("服务器已在重启中")
        _restart_pending=True; restart_id=uuid.uuid4().hex
        script="import time,subprocess,sys; time.sleep(1); subprocess.Popen([sys.executable, sys.argv[1]], cwd=sys.argv[2], env=None); time.sleep(1)"
        subprocess.Popen([sys.executable,"-c",script,str(Path(__file__).resolve().parents[1]/"server.py"),str(Path(__file__).resolve().parents[2])], cwd=str(Path(__file__).resolve().parents[2]), env=os.environ.copy(), creationflags=getattr(subprocess,"CREATE_NEW_PROCESS_GROUP",0))
        threading.Timer(0.4, os._exit, args=(0,)).start()
        ctx.request.send_json(202,{"ok":True,"restart_id":restart_id,"status":"scheduled"}); return True
