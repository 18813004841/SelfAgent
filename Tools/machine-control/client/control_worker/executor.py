from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
from pathlib import Path
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
    name = os.path.basename(parts[0].strip('"')) if parts else ""
    return name[:-4] if name.lower().endswith(".exe") else name


def run_shell(payload: Dict[str, Any], allowed: set[str] | None = None,
              cancel_event: threading.Event | None = None) -> Dict[str, Any]:
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
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + timeout
        reason = None
        while True:
            if cancel_event is not None and cancel_event.is_set():
                reason = "cancelled"
            elif time.monotonic() >= deadline:
                reason = "timeout"
            if reason:
                cleanup_error = None
                if os.name == "nt":
                    try:
                        cleanup = subprocess.run(
                            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                            capture_output=True, text=True, timeout=10,
                        )
                        if cleanup.returncode != 0:
                            cleanup_error = (cleanup.stderr or cleanup.stdout or "taskkill failed").strip()
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        cleanup_error = str(exc)
                else:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                # A descendant can retain inherited pipes after the shell exits;
                # never block cancellation waiting for those pipes to close.
                stdout, stderr = "", ""
                result = {"ok": False, "exit_code": 130 if reason == "cancelled" else 124,
                        "stdout": (stdout or "")[-20000:], "stderr": reason,
                        "cancelled": reason == "cancelled",
                        "duration_sec": round(time.time() - started, 3)}
                if cleanup_error:
                    result["cleanup_error"] = cleanup_error
                    result["stderr"] = f"{reason}; process cleanup failed: {cleanup_error}"
                return result
            try:
                stdout, stderr = proc.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                continue
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": (stdout or "")[-20000:],
            "stderr": (stderr or "")[-20000:],
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


def execute_task(kind: str, payload: Dict[str, Any], allowed: set[str] | None = None,
                 cancel_event: threading.Event | None = None) -> Dict[str, Any]:
    if kind == "shell":
        return run_shell(payload, allowed, cancel_event)
    if kind == "read_build_log":
        return read_build_log(payload)
    return {"ok": False, "error": f"unsupported task kind: {kind}"}


def read_build_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Read a Unity log below the supplied worktree without allowing path escape."""
    worktree = Path(str(payload.get("worktree_path", "")).strip()).expanduser()
    relative = str(payload.get("relative_path", "Game/BuildFolder/BuildTemporary/Unity.log"))
    if not worktree.is_dir() or Path(relative).is_absolute():
        return {"ok": False, "error": "invalid worktree or relative log path"}
    try:
        root = worktree.resolve(strict=True)
        target = (root / relative).resolve(strict=True)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    if not target.is_file() or (target != root and root not in target.parents):
        return {"ok": False, "error": "log path is outside worktree or does not exist"}
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "path": str(target), "text": text[-500000:]}
