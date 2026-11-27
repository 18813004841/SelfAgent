#!/usr/bin/env python3
"""在临时 Git 仓库中验证发现问题和执行异常时的基线行为。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


ROOT = Path(__file__).resolve().parents[1]
REVIEW_ROOT = ROOT / "workbench" / "machine-dashboard-server" / "tools" / "code-review-agent"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        prompt = body["input"][-1]["content"] if isinstance(body.get("input"), list) else ""
        findings = []
        if "GameObject.Find" in prompt:
            findings.append({
                "severity": "high",
                "message": "Runtime 使用 GameObject.Find",
                "file": "Game/Assets/Bad.cs",
                "line": 1,
                "rule": "Runtime 代码不得引用 UnityEditor",
                "suggestion": "移除 UnityEditor",
                "confidence": 1,
            })
        payload = {"output_text": json.dumps({"findings": findings}, ensure_ascii=False)}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        return


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True)


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    work = Path(tempfile.mkdtemp(prefix="selfagent-review-"))
    review_root = work / "review-tool"
    shutil.copytree(REVIEW_ROOT / "code_review", review_root / "code_review", ignore=shutil.ignore_patterns("__pycache__", "log"))
    project = work / "project"
    project.mkdir()
    run(["git", "init", "-b", "main"], project)
    run(["git", "config", "user.email", "review@example.com"], project)
    run(["git", "config", "user.name", "Review Validation"], project)
    skill = project / "SKILL.md"
    skill.write_text("Runtime 代码不得引用 UnityEditor\n", encoding="utf-8")
    source = project / "Game" / "Assets"
    source.mkdir(parents=True)
    (source / "Good.cs").write_text("public class Good {}\n", encoding="utf-8")
    run(["git", "add", "."], project)
    run(["git", "commit", "-m", "base"], project)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
    (source / "Good.cs").write_text("public class Good { public int Value; }\n", encoding="utf-8")
    run(["git", "add", "."], project)
    run(["git", "commit", "-m", "good increment"], project)
    good = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
    config = {
        "project": {"name": "validation", "path": str(project), "branch": "main", "remote": "none"},
        "model_service": {"api_url": f"http://127.0.0.1:{port}/v1", "model": "validation", "timeout_seconds": 10, "max_output_tokens": 300, "api_key": "test-key"},
        "checks": {"compile_command": None, "skill_paths": [str(skill)], "failure_threshold": "high"},
        "storage": {"state_file": "state.json", "report_dir": "reports"},
    }
    config_path = work / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(review_root), str(ROOT / "workbench" / "machine-dashboard-server" / "src"), env.get("PYTHONPATH"))))
    env["WORKBENCH_CODE_REVIEW_DATA_DIR"] = str(review_root / "validation-data")
    env["WORKBENCH_CODE_REVIEW_LOG_DIR"] = str(review_root / "validation-logs")
    first = subprocess.run([sys.executable, "-m", "code_review.cli", "check", "--config", str(config_path)], cwd=review_root, env=env, text=True, capture_output=True)
    (source / "Bad.cs").write_text("public class Bad { void Start(){ UnityEditor.AssetDatabase.Refresh(); } }\n", encoding="utf-8")
    run(["git", "add", "."], project)
    run(["git", "commit", "-m", "bad"], project)
    # Simulate an unexpected notification exception in the isolated tool copy.
    with (review_root / "code_review" / "feishu.py").open("a", encoding="utf-8") as module:
        module.write("\ndef notify(findings, threshold, webhook=None, task_name=None, status=None):\n    raise RuntimeError('simulated notification failure')\n")
    second = subprocess.run([sys.executable, "-m", "code_review.cli", "check", "--config", str(config_path)], cwd=review_root, env=env, text=True, capture_output=True)
    bad = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
    report_path = review_root / "validation-data" / f"{project.name}-main" / "reports" / f"{project.name}-main-0002" / "result.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    notification_failure_saved = bool(report.get("问题内容")) and "飞书通知发送失败：通知处理发生异常" in report.get("警告", [])
    state_path = review_root / "validation-data" / f"{project.name}-main" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    finding_advanced_baseline = state.get("last_successful_sha") == bad
    (source / "Good.cs").write_text("public class Good { public int More; }\n", encoding="utf-8")
    run(["git", "add", "."], project)
    run(["git", "commit", "-m", "next increment"], project)
    config["checks"]["skill_paths"] = [str(work / "missing-skill")]
    config_path.write_text(json.dumps(config), encoding="utf-8")
    third = subprocess.run([sys.executable, "-m", "code_review.cli", "check", "--config", str(config_path)], cwd=review_root, env=env, text=True, capture_output=True)
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    failure_preserved_baseline = final_state.get("last_successful_sha") == bad
    print(json.dumps({
        "workspace": str(work),
        "first_exit": first.returncode,
        "second_exit": second.returncode,
        "baseline_sha": state.get("last_successful_sha"),
        "passed_sha": good,
        "finding_advanced_baseline": finding_advanced_baseline,
        "third_exit": third.returncode,
        "failure_preserved_baseline": failure_preserved_baseline,
        "notification_failure_report_saved": notification_failure_saved,
        "first_stdout": first.stdout[-1500:],
        "first_stderr": first.stderr[-1500:],
        "second_stdout": second.stdout[-1500:],
        "second_stderr": second.stderr[-1500:],
    }, ensure_ascii=False, indent=2))
    server.shutdown()
    return 0 if first.returncode == 0 and second.returncode == 0 and third.returncode == 1 and finding_advanced_baseline and failure_preserved_baseline and notification_failure_saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
