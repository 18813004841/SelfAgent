from __future__ import annotations

import json, os, re, threading, time
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Any
from core.Log.log_helper import get_view_logger

logger = get_view_logger("package_error_analysis")
_lock = threading.RLock()

def _store():
    from core.sqlite_db import SqliteDB
    return SqliteDB()

def _save(task: dict[str, Any]) -> None:
    data = {"status": task.get("status", "queued"), "input_text": task.get("input_text", ""), "events_json": json.dumps(task.get("events", []), ensure_ascii=False), "result_json": json.dumps(task.get("result") or {}, ensure_ascii=False), "error": task.get("error", ""), "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    with _store() as db:
        if db.get("package_error_analyses", "id", task["id"]):
            db.update("package_error_analyses", data, "id=?", (task["id"],))
        else:
            db.insert("package_error_analyses", {"id": task["id"], **data})

def _load(task_id: str) -> dict[str, Any]:
    with _store() as db: row = db.get("package_error_analyses", "id", task_id)
    if not row: raise KeyError(task_id)
    row["events"] = json.loads(row.pop("events_json") or "[]")
    row["result"] = json.loads(row.pop("result_json") or "{}")
    row["input"] = json.loads(row.get("input_text") or "{}") if str(row.get("input_text", "")).startswith("{") else row.get("input_text")
    return row

def _event(task, message, status="running", data=None):
    item = {"time": time.strftime("%H:%M:%S"), "message": message, "status": status}
    if data: item["data"] = data
    task["events"].append(item)
    task["updated_at"] = time.time()
    _save(task)

def _json_request(url, token="", method="GET", payload=None, extra_headers=None):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    if extra_headers: headers.update(extra_headers)
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    return json.loads(urlopen(Request(url, data=data, method=method, headers=headers), timeout=10).read())

def resolve_jenkins(info: dict[str, Any]) -> dict[str, Any]:
    """Read Jenkins build parameters when credentials are configured; never log credentials."""
    url = info.get("jenkins_url")
    if not url or os.environ.get("JENKINS_USERNAME") is None or os.environ.get("JENKINS_API_TOKEN") is None:
        return {}
    import base64
    auth = base64.b64encode(f"{os.environ['JENKINS_USERNAME']}:{os.environ['JENKINS_API_TOKEN']}".encode()).decode()
    response = _json_request(url.rstrip("/") + "/api/json?tree=number,actions[parameters[name,value]],builtOn", extra_headers={"Authorization": f"Basic {auth}"})
    params = {}
    for action in response.get("actions", []):
        for item in action.get("parameters", []) or []:
            if item.get("name") and item.get("value") is not None: params[str(item["name"])] = str(item["value"])
    version = params.get("Version") or params.get("VERSION") or info.get("version")
    number = str(response.get("number") or info.get("build_number") or "")
    return {
        "version": version,
        "build_number": number,
        "bundle": info.get("bundle") or (f"{version}.{number}" if version and number else ""),
        "platform": params.get("platform") or params.get("Platform"),
        "branch": params.get("branch") or params.get("Branch"),
        "target_ip": params.get("target_ip"),
        "worktree_path": params.get("worktree_path"),
        "built_on": response.get("builtOn"),
    }

def parse_input(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"raw": text}
    url = re.search(r"https?://[^\s)]+", text)
    if url: result["jenkins_url"] = url.group(0).rstrip("\\)]},.;")
    for key in ("target_ip", "worktree_path"):
        m = re.search(rf"{key}\s*:\s*([^\s\\]+)", text, re.I)
        if m: result[key] = m.group(1).strip('"')
    for key in ("version", "bundle", "Version", "BundleVersion"):
        m = re.search(rf"(?:{key})\s*[:=]\s*([\w.\-]+)", text, re.I)
        if m: result["bundle" if key.lower().startswith("bundle") else "version"] = m.group(1)
    m = re.search(r"(?:Build|构建号)\s*[:#]?\s*(\d+)", text, re.I)
    if m: result["build_number"] = m.group(1)
    m = re.search(r"(?:平台|platform)\s*[:=]\s*([\w-]+)", text, re.I)
    if m: result["platform"] = m.group(1)
    m = re.search(r"(?:分支|branch)\s*[:=]\s*([^\s\\]+)", text, re.I)
    if m: result["branch"] = m.group(1).strip('"')
    if "bundle" not in result and result.get("version") and result.get("build_number"):
        result["bundle"] = f"{result['version']}.{result['build_number']}"
    return result

def _safe_log_path(root: Path, candidate: Path) -> Path | None:
    try:
        root = root.expanduser().resolve()
        path = candidate.expanduser().resolve(strict=True)
        return path if path.is_file() and (root == path or root in path.parents) else None
    except OSError:
        return None

def _find_mounted_log(info: dict[str, Any]) -> tuple[Path | None, str]:
    bundle = info.get("bundle", "")
    branch = info.get("branch", "master")
    platform = info.get("platform", "Android")
    names = [f"{bundle}.unity.log", f"{bundle}.Global.unity.log"]
    for root_text in (os.environ.get("BUILD_PACKAGE_MAC_ROOT", "/Volumes/kg-hd/KoA"), os.environ.get("BUILD_PACKAGE_WINDOWS_ROOT", "/z/KoA")):
        root = Path(root_text)
        for name in names:
            candidate = root / platform / "Master" / branch / name
            safe = _safe_log_path(root, candidate)
            if safe: return safe, f"mounted:{safe}"
    return None, "mounted:not-found"

def _analyse_log(log: str, info: dict[str, Any]) -> dict[str, Any]:
    lines = log.splitlines()
    patterns = [
        ("SDK模块", r"BuildFolder[\\/]BuildTemporary|SDK|toolchain"),
        ("C#编译", r"error CS\d+|\.cs\(\d+,\d+\)"),
        ("Gradle", r"Gradle|Execution failed for task|manifest merger"),
        ("IL2CPP", r"IL2CPP|il2cpp"),
        ("签名", r"signing|keystore|apksigner|codesign"),
        ("Xcode", r"Xcode|xcodebuild"),
    ]
    hits = []
    for i, line in enumerate(lines):
        for step, pattern in patterns:
            if re.search(pattern, line, re.I): hits.append((i, step, line.strip()))
    if not hits:
        return {"failure_reason": "日志中未找到可确认的底层失败信号", "failed_step": "未识别", "evidence": lines[-20:]}
    index, step, line = hits[0]
    evidence = [x.strip() for x in lines[max(0, index-3): min(len(lines), index+17)] if x.strip()][:20]
    return {"failure_reason": line, "failed_step": step, "evidence": evidence, "requires_project": step in {"SDK模块", "C#编译"}}

def _codex_summary(result: dict[str, Any], info: dict[str, Any]) -> dict[str, str]:
    """Optionally turn deterministic facts into readable Chinese; facts remain authoritative."""
    if os.environ.get("BUILD_PACKAGE_FAIL_CODEX", "").lower() not in {"1", "true", "yes", "on"}:
        return {}
    try:
        from integrations.codex_cli.client import CodexCliClient
        prompt = json.dumps({"task": "解释 Unity 打包失败", "facts": {"step": result.get("failed_step"), "reason": result.get("failure_reason"), "evidence": result.get("evidence", [])}}, ensure_ascii=False)
        response = CodexCliClient(timeout=120).execute(
            "只根据以下 JSON 事实输出 JSON，字段 failure_reason 和 repair_suggestion；不要新增文件、错误码、渠道或证据：\n" + prompt,
            cwd=Path.cwd(),
        ).text
        match = re.search(r"\{.*\}", response, re.S)
        data = json.loads(match.group(0)) if match else {}
        return {k: str(data[k]) for k in ("failure_reason", "repair_suggestion") if data.get(k)}
    except Exception as exc:
        logger.warning("package_analysis.codex.failed: %s", exc)
        return {}

def _run(analysis_id: str, text: str) -> None:
    task = _load(analysis_id)
    try:
        _event(task, "开始解析 Jenkins / 飞书输入")
        info = parse_input(text)
        try:
            jenkins = {k: v for k, v in resolve_jenkins(info).items() if v}
            info.update(jenkins)
            if jenkins: _event(task, "Jenkins 构建参数补全完成", data={k: v for k, v in jenkins.items() if k != "raw"})
        except Exception as exc:
            _event(task, f"Jenkins 参数读取失败，继续使用已有输入：{exc}", "warning")
        task["input"] = {k: v for k, v in info.items() if k != "raw"}
        task["input_text"] = json.dumps(task["input"], ensure_ascii=False)
        _event(task, "输入解析完成", data={k: v for k, v in info.items() if k != "raw"})
        log_path = None
        target = info.get("target_ip")
        center = os.environ.get("MACHINE_CONTROL_CENTER")
        token = os.environ.get("MACHINE_CONTROL_TOKEN", "")
        remote_text = None
        if target and center:
            try:
                workers = _json_request(center.rstrip("/") + "/api/workers", token).get("workers", [])
                matched = [w for w in workers if w.get("status") == "online" and target in w.get("meta", {}).get("local_ips", [])]
                _event(task, f"Worker 查询完成：{'已匹配' if matched else '未匹配'}")
                if matched and info.get("worktree_path"):
                    payload = {"worktree_path": info["worktree_path"], "relative_path": "Game/BuildFolder/BuildTemporary/Unity.log"}
                    created = _json_request(center.rstrip("/") + "/api/tasks", token, "POST", {"machine_id": matched[0].get("worker_id") or matched[0].get("machine_id"), "kind": "read_build_log", "payload": payload})
                    remote_task_id = created.get("task", {}).get("task_id")
                    if remote_task_id:
                        deadline = time.time() + 120
                        while time.time() < deadline:
                            remote = _json_request(center.rstrip("/") + f"/api/tasks/{remote_task_id}", token).get("task", {})
                            if remote.get("status") in {"succeeded", "failed", "cancelled"}:
                                if remote.get("status") == "succeeded" and remote.get("result", {}).get("ok"):
                                    remote_text = remote["result"].get("text", "")
                                break
                            time.sleep(1)
                    _event(task, "Worker 日志读取完成" if remote_text is not None else "Worker 日志读取失败，转入网盘", "running")
            except Exception as exc: _event(task, f"Worker 查询失败，转入网盘：{exc}", "warning")
        else: _event(task, "未配置在线 Worker 查询，转入网盘")
        if remote_text is not None:
            log_text = remote_text; _event(task, "使用在线 Worker 日志")
        else:
            log_path, source = _find_mounted_log(info)
            _event(task, f"网盘日志查找完成：{source}")
            if not log_path: raise RuntimeError("分析失败：无法获得打包日志")
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        result = _analyse_log(log_text, info)
        result.update(_codex_summary(result, info))
        task["result"] = result
        _event(task, "失败 step 与核心证据分析完成", "completed")
        task["status"] = "completed"
        _save(task)
    except Exception as exc:
        task["error"] = str(exc); task["status"] = "failed"; _event(task, str(exc), "failed"); _save(task)

def create_task(text: str) -> dict[str, Any]:
    task = {"id": f"analysis_{int(time.time()*1000)}", "status": "queued", "events": [], "input_text": text, "result": {}, "error": ""}
    _save(task)
    threading.Thread(target=_run, args=(task["id"], text), daemon=True).start()
    return task

def get_task(task_id: str) -> dict[str, Any]:
    return _load(task_id)

def list_tasks(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent analysis tasks for the dashboard list view."""
    with _store() as db:
        rows = db.query(
            "SELECT id, status, input_text, result_json, error, updated_at "
            "FROM package_error_analyses ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(int(limit), 200)),),
        )
    tasks = []
    for row in rows:
        item = dict(row)
        item["result"] = json.loads(item.pop("result_json") or "{}")
        item["input"] = item.pop("input_text", "")
        tasks.append(item)
    return tasks
