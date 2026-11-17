"""代码检查 CLI 集成边界。"""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path


class CodeReviewCli:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def run(self, payload: dict, *, timeout: float = 900) -> dict:
        if timeout <= 0:
            raise ValueError("timeout 必须大于 0")
        command = [sys.executable, str(self.root / "run_task.py"), "--input", json.dumps(payload, ensure_ascii=False)]
        env = os.environ.copy()
        env["PYTHONPATH"] = str(self.root) + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(command, cwd=self.root, env=env, capture_output=True,
                                   text=True, encoding="utf-8", timeout=timeout)
        if not completed.stdout.strip():
            raise RuntimeError(completed.stderr.strip() or "代码检查 CLI 未返回结果")
        try:
            result = json.loads(completed.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError as exc:
            raise RuntimeError("代码检查 CLI 返回了无效 JSON") from exc
        if not isinstance(result, dict):
            raise RuntimeError("代码检查 CLI 结果必须是 JSON 对象")
        if completed.returncode not in {0, 1}:
            raise RuntimeError(f"代码检查 CLI 异常退出: {completed.returncode}")
        return result

