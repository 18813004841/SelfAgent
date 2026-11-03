from __future__ import annotations

import os
import shlex
import subprocess
import time
from typing import Any, Dict, List

DEFAULT_ALLOWED_COMMANDS = {
    # cross-platform basics
    "echo", "pwd", "python", "python3", "git", "hostname", "whoami",
    # build/test tools
    "unity", "adb",
    # log/file inspection helpers for Mac/Linux workers
    "tail", "ls", "cat", "grep", "find", "df", "du",
    # iOS/macOS build helpers
    "xcodebuild", "security", "codesign", "plutil",
}


def _command_name(command: str) -> str:
    try:
        parts = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        parts = command.split()
    return os.path.basename(parts[0]) if parts else ""


def run_shell(payload: Dict[str, Any], allowed: set[str] | None = None) -> Dict[str, Any]:
    command = payload.get("command", "")
    timeout = int(payload.get("timeout", 60))
    cwd = payload.get("cwd") or None
    allowed = allowed or DEFAULT_ALLOWED_COMMANDS
    name = _command_name(command)
    if name not in allowed:
        return {
            "ok": False,
            "exit_code": 126,
            "stdout": "",
            "stderr": f"command not allowed: {name}",
        }
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-20000:],
            "stderr": proc.stderr[-20000:],
            "duration_sec": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired as e:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": (e.stdout or "")[-20000:] if isinstance(e.stdout, str) else "",
            "stderr": f"timeout after {timeout}s",
            "duration_sec": round(time.time() - started, 3),
        }


def execute_task(kind: str, payload: Dict[str, Any], allowed: set[str] | None = None) -> Dict[str, Any]:
    if kind == "shell":
        return run_shell(payload, allowed)
    return {"ok": False, "error": f"unsupported task kind: {kind}"}
