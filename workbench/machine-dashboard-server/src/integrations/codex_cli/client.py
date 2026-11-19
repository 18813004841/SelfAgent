from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class CodexCliError(RuntimeError):
    """Codex CLI 启动、执行或返回结果异常。"""


@dataclass
class CodexCliResult:
    events: list[dict[str, Any]]
    messages: list[str]
    returncode: int
    pid: int | None = None

    @property
    def text(self) -> str:
        return self.messages[-1] if self.messages else ""


class CodexCliClient:
    """执行一次 Codex CLI 任务；不启动或管理 app-server。"""

    def __init__(self, *, executable: str | None = None, model: str | None = None,
                 sandbox: str = "read-only", timeout: float = 900) -> None:
        self.executable = executable or os.environ.get("WORKBENCH_CODEX_EXECUTABLE")
        self.model = model
        self.sandbox = sandbox
        self.timeout = timeout

    def resolve_executable(self) -> str:
        command = self.executable or (shutil.which("codex.cmd") if os.name == "nt" else shutil.which("codex")) or shutil.which("codex")
        if not command:
            raise CodexCliError("找不到 Codex CLI，请安装 codex 并加入 PATH")
        return command

    def execute(self, prompt: str, *, cwd: str | Path, session_id: str | None = None,
                cancel: Callable[[], bool] | None = None,
                on_event: Callable[[dict[str, Any]], None] | None = None) -> CodexCliResult:
        project = Path(cwd).resolve()
        command = self.resolve_executable()
        args = [command, "exec"]
        if session_id:
            args += ["resume", session_id]
        args += ["--json", "--skip-git-repo-check"]
        if not session_id:
            args += ["-C", str(project)]
        args += ["-s", self.sandbox]
        if self.model:
            args += ["-m", self.model]
        proc: subprocess.Popen[str] | None = None
        events: list[dict[str, Any]] = []
        try:
            proc = subprocess.Popen(args, cwd=str(project), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
            def read_output() -> None:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        event = {"type": "output", "text": line}
                    events.append(event)
                    if on_event:
                        on_event(event)
            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            started = time.monotonic()
            while proc.poll() is None:
                if cancel and cancel():
                    proc.terminate()
                    raise CodexCliError("Codex 检查已取消")
                if time.monotonic() - started > self.timeout:
                    proc.terminate()
                    raise CodexCliError("Codex 检查超时")
                time.sleep(0.05)
            reader.join(timeout=2)
            code = proc.wait(timeout=10)
            messages = [str(e["item"]["text"]) for e in events
                        if isinstance(e.get("item"), dict) and e["item"].get("type") == "agent_message" and e["item"].get("text")]
            if code != 0:
                raise CodexCliError(f"Codex 进程失败，退出码 {code}")
            if not messages:
                raise CodexCliError("Codex 未返回审查结果")
            return CodexCliResult(events, messages, code, proc.pid)
        except subprocess.TimeoutExpired as exc:
            raise CodexCliError("Codex 检查超时") from exc
        except OSError as exc:
            raise CodexCliError(str(exc)) from exc
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
