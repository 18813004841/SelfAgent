from __future__ import annotations

import json, os, re, sys, threading, time
from urllib.request import Request, urlopen
from pathlib import Path
from typing import Any, TypedDict
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
        m = re.search(rf'{key}\s*[:=]\s*(?:"([^"\r\n]+)"|([^\s]+))', text, re.I)
        if m: result[key] = m.group(1) or m.group(2)
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
    if not bundle or not re.fullmatch(r"[\w.\-]+", bundle):
        return None, "mounted:missing-bundle"
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
    failure_signal = re.compile(r"\berror\b|\bfailed\b|\bfailure\b|\bexception\b|error CS\d+", re.I)
    for i, line in enumerate(lines):
        if not failure_signal.search(line):
            continue
        for step, pattern in patterns:
            if re.search(pattern, line, re.I):
                hits.append((i, step, line.strip()))
                break
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

class AnalysisState(TypedDict, total=False):
    task: dict[str, Any]
    text: str
    info: dict[str, Any]
    log_text: str | None
    result: dict[str, Any]


def _parse_node(state: AnalysisState) -> dict[str, Any]:
    task, text = state["task"], state["text"]
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
    return {"info": info}


def _archive_node(state: AnalysisState) -> dict[str, Any]:
    task, info = state["task"], state["info"]
    log_text = None
    log_path, source = _find_mounted_log(info)
    if log_path:
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            if not log_text.strip():
                log_text = None
                _event(task, "网盘日志为空，转入打包机", "warning")
            else:
                _event(task, f"网盘日志查找完成：{source}")
                _event(task, "使用网盘归档日志")
        except OSError as exc:
            _event(task, f"网盘日志读取失败，转入打包机：{exc}", "warning")
    else:
        _event(task, f"网盘日志查找完成：{source}，转入打包机", "warning")
    return {"log_text": log_text}


def _worker_node(state: AnalysisState) -> dict[str, Any]:
    from integrations.codex_cli import CodexCliClient

    task, info = state["task"], state["info"]
    target, worktree = info.get("target_ip"), info.get("worktree_path")
    if not target or not worktree:
        raise RuntimeError("缺少 target_ip 或 worktree_path，无法读取打包机日志")
    control_root = Path(__file__).resolve().parents[4] / "Tools" / "machine-control"
    mcp_python = control_root / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    center = os.environ.get("MACHINE_CONTROL_SERVER_URL", f"http://127.0.0.1:{os.environ.get('MACHINE_CONTROL_PORT', '18765')}").rstrip("/")
    token = os.environ.get("MACHINE_CONTROL_TOKEN", "dev-token")
    quote = lambda value: json.dumps(str(value), ensure_ascii=False)
    args = ["-m", "control_mcp.server", "--server", center, "--token", token]
    config = {
        "mcp_servers.machine_control.default_tools_approval_mode": quote("approve"),
        "mcp_servers.machine_control.command": quote(mcp_python if mcp_python.is_file() else sys.executable),
        "mcp_servers.machine_control.args": "[" + ", ".join(quote(x) for x in args) + "]",
        "mcp_servers.machine_control.env.PYTHONPATH": quote(str(control_root / "server") + os.pathsep + str(control_root / "shared")),
        "mcp_servers.machine_control.env.MACHINE_CONTROL_LOG_TARGET": quote(target),
        "mcp_servers.machine_control.env.MACHINE_CONTROL_LOG_WORKTREE": quote(worktree),
    }
    _event(task, "开始通过 Codex 和中央服务器 MCP 提交日志读取任务")
    try:
        started_ms = int(time.time() * 1000)
        reply = CodexCliClient(timeout=180).execute(
            "通过已连接的 machine_control MCP 调用唯一提供的 submit_build_log 工具一次。"
            "只输出 JSON 对象，包含工具返回的 ok、task_id 或 error。"
            "不要调用其他工具、编造结果、修改文件或执行命令。",
            cwd=control_root, config_overrides=config, ignore_user_config=True,
        )
        response = json.loads(reply.text.strip())
        task_id = response.get("task_id") if response.get("ok") is True else None
        if not isinstance(task_id, str) or not re.fullmatch(r"task_[A-Za-z0-9_-]+", task_id):
            raise RuntimeError("Codex 未返回有效的中央服务器任务 ID")
        _event(task, "MCP 读取任务已提交，等待中央服务器结果")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            remote = _json_request(center + f"/api/tasks/{task_id}", token).get("task", {})
            payload = remote.get("payload") or {}
            workers = _json_request(center + "/api/workers", token).get("workers", [])
            matched = [w for w in workers if w.get("machine_id") == remote.get("machine_id") and target in (w.get("meta", {}).get("local_ips", []) or [])]
            if int(remote.get("created_at") or 0) < started_ms - 1000 or remote.get("kind") != "read_build_log" or payload.get("worktree_path") != worktree or payload.get("relative_path") != "Game/BuildFolder/BuildTemporary/Unity.log" or len(matched) != 1:
                raise RuntimeError("中央服务器任务与目标机器或日志路径不匹配")
            if remote.get("status") in {"succeeded", "failed", "cancelled"}:
                result = remote.get("result") or {}
                text = result.get("text")
                if remote.get("status") == "succeeded" and result.get("ok") and isinstance(text, str) and text.strip():
                    _event(task, "Worker 日志读取完成，使用在线 Worker 日志（请核对构建版本）")
                    return {"log_text": text}
                raise RuntimeError("打包机日志读取失败或为空")
            time.sleep(1)
        raise RuntimeError("等待打包机日志超时；远程任务可能仍在执行")
    except Exception as exc:
        logger.warning("package_analysis.worker.failed task_id=%s error_type=%s", task["id"], type(exc).__name__)
        raise RuntimeError("通过 Codex 和中央服务器 MCP 获取打包机日志失败，请检查服务与目标机器配置") from exc


def _analysis_node(state: AnalysisState) -> dict[str, Any]:
    result = _analyse_log(state["log_text"], state["info"])
    summary = _codex_summary(result, state["info"])
    if summary.get("repair_suggestion"):
        result["repair_suggestion"] = summary["repair_suggestion"]
    enabled = os.environ.get("BUILD_PACKAGE_FAIL_CODEX", "").lower() in {"1", "true", "yes", "on"}
    _event(state["task"], "模型建议：已生成" if summary.get("repair_suggestion") else ("模型建议：未生成，保留规则分析结果" if enabled else "模型建议：未启用，已跳过"))
    return {"result": result}


def _result_node(state: AnalysisState) -> dict[str, Any]:
    task = state["task"]
    task["result"] = state["result"]
    _event(task, "失败 step 与核心证据分析完成", "completed")
    return {}



def _logged_node(name, label, node):
    """Persist node lifecycle for the task UI and write concise operational logs."""
    def execute(state):
        task = state["task"]
        started = time.monotonic()
        _event(task, f"{label}：开始", data={"node": name, "phase": "start"})
        logger.info("package_analysis.node.begin task_id=%s node=%s", task["id"], name)
        try:
            output = node(state)
        except Exception as exc:
            elapsed_ms = round((time.monotonic() - started) * 1000)
            _event(task, f"{label}：结束，执行失败（{type(exc).__name__}，耗时 {elapsed_ms} ms）", "failed", data={"node": name, "phase": "failed"})
            logger.error("package_analysis.node.failed task_id=%s node=%s elapsed_ms=%s error_type=%s", task["id"], name, elapsed_ms, type(exc).__name__)
            raise
        elapsed_ms = round((time.monotonic() - started) * 1000)
        if name == "archive":
            outcome = "已获取归档日志" if output.get("log_text") else "归档不可用，将尝试打包机"
        elif name == "worker":
            outcome = "已获取打包机日志"
        elif name == "parse":
            outcome = "输入参数已解析"
        elif name == "analysis":
            result = output["result"]
            outcome = f"失败阶段：{result.get('failed_step', '未识别')}，证据 {len(result.get('evidence', []))} 条"
        else:
            outcome = "分析结果已保存"
        if name == "save_result":
            task["status"] = "completed"
        _event(task, f"{label}：结束，{outcome}（耗时 {elapsed_ms} ms）", "completed", data={"node": name, "phase": "completed"})
        logger.info("package_analysis.node.end task_id=%s node=%s elapsed_ms=%s", task["id"], name, elapsed_ms)
        if name == "archive" and output.get("log_text"):
            _event(task, "读取打包机日志：已跳过，已使用归档日志", data={"node": "worker", "phase": "skipped"})
        return output
    return execute

def _build_graph():
    # Lazy import keeps unrelated workbench features available if the optional
    # runtime dependency is missing; the analysis task reports the failure.
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError("打包分析需要 LangGraph，请安装workbench/machine-dashboard-server/requirements.txt 中的 langgraph") from exc
    graph = StateGraph(AnalysisState)
    graph.add_node("parse", _logged_node("parse", "解析输入和补全参数", _parse_node))
    graph.add_node("archive", _logged_node("archive", "读取归档日志", _archive_node))
    graph.add_node("worker", _logged_node("worker", "读取打包机日志", _worker_node))
    graph.add_node("analysis", _logged_node("analysis", "分析日志", _analysis_node))
    graph.add_node("save_result", _logged_node("save_result", "保存分析结果", _result_node))
    graph.add_edge(START, "parse")
    graph.add_edge("parse", "archive")
    graph.add_conditional_edges("archive", lambda state: "analysis" if state.get("log_text") else "worker", {"analysis": "analysis", "worker": "worker"})
    graph.add_edge("worker", "analysis")
    graph.add_edge("analysis", "save_result")
    graph.add_edge("save_result", END)
    return graph.compile()


def _run(analysis_id: str, text: str) -> None:
    task = _load(analysis_id)
    try:
        _build_graph().invoke({"task": task, "text": text})
    except Exception as exc:
        logger.error("package_analysis.run.failed task_id=%s error=%s", analysis_id, exc)
        task["error"] = str(exc)
        task["status"] = "failed"
        _event(task, str(exc), "failed")
        _save(task)

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
