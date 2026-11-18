#!/usr/bin/env python3
"""验证服务器 Codex runner 的成功、非法输出、超时和取消路径。"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench/machine-dashboard-server/tools/code-review-agent"))
from code_review.codex_runner import CodexRunner, CodexRunnerError


def make_command(folder: Path, body: str) -> str:
    path = folder / ("fake-codex.cmd" if os.name == "nt" else "fake-codex")
    if os.name == "nt":
        path.write_text("@echo off\n" + body, encoding="ascii")
    else:
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="codex-runner-") as raw:
        folder = Path(raw)
        good = make_command(folder, "echo {\"item\":{\"type\":\"agent_message\",\"text\":\"{\\\"findings\\\":[]}\"}}")
        assert '"findings":[]' in CodexRunner(ROOT, executable=good, timeout=3).run("check")
        bad = make_command(folder, "exit 7")
        try:
            CodexRunner(ROOT, executable=bad, timeout=3).run("check")
        except CodexRunnerError:
            pass
        else:
            raise AssertionError("non-zero Codex exit was accepted")
        slow = make_command(folder, "ping -n 20 127.0.0.1 >nul") if os.name == "nt" else make_command(folder, "sleep 20")
        try:
            CodexRunner(ROOT, executable=slow, timeout=0.1).run("check")
        except CodexRunnerError as exc:
            assert "超时" in str(exc)
        else:
            raise AssertionError("Codex timeout was not enforced")
        try:
            CodexRunner(ROOT, executable=slow, timeout=3).run("check", cancel=lambda: True)
        except CodexRunnerError as exc:
            assert "取消" in str(exc)
        else:
            raise AssertionError("Codex cancellation was not enforced")
    print("codex_runner validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
