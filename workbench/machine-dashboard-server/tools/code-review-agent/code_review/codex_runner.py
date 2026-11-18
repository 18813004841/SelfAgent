from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable


class CodexRunnerError(RuntimeError):
    pass


class CodexRunner:
    """Run the server-local Codex CLI without exposing a model HTTP endpoint."""

    def __init__(self, project: Path, timeout: float = 900, executable: str | None = None,
                 model: str | None = None, sandbox: str = "read-only") -> None:
        self.project = project
        self.timeout = timeout
        self.executable = executable or os.environ.get("WORKBENCH_CODEX_EXECUTABLE")
        self.model = model
        self.sandbox = sandbox

    def run(self, prompt: str, cancel: Callable[[], bool] | None = None,
            on_event: Callable[[dict[str, Any]], None] | None = None) -> str:
        command = self.executable or (shutil.which("codex.cmd") if os.name == "nt" else shutil.which("codex")) or shutil.which("codex")
        if not command:
            raise CodexRunnerError("找不到服务器 Codex CLI，请安装 codex 并加入 PATH")
        # Current Codex CLI no longer accepts the legacy ``-a never`` option;
        # passing it makes Windows npm wrappers fail before starting Codex.
        args = [command, "exec", "--json", "--skip-git-repo-check", "-C", str(self.project), "-s", self.sandbox]
        if self.model:
            args.extend(["-m", self.model])
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(args, cwd=str(self.project), stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace")
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
            events: list[dict[str, Any]] = []
            started = time.monotonic()
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
            while proc.poll() is None:
                if cancel and cancel():
                    proc.terminate()
                    proc.wait(timeout=5)
                    raise CodexRunnerError("Codex 检查已取消")
                if time.monotonic() - started > self.timeout:
                    proc.terminate()
                    proc.wait(timeout=5)
                    raise CodexRunnerError("Codex 检查超时")
                time.sleep(0.05)
            reader.join(timeout=2)
            returncode = proc.wait(timeout=10)
            if returncode != 0:
                raise CodexRunnerError(f"Codex 进程失败，退出码 {returncode}")
            texts = []
            diagnostics = []
            for event in events:
                item = event.get("item") if isinstance(event, dict) else None
                if isinstance(item, dict) and item.get("type") == "agent_message" and item.get("text"):
                    texts.append(str(item["text"]))
                elif event.get("type") == "output" and event.get("text"):
                    diagnostics.append(str(event["text"]))
            if not texts:
                raise CodexRunnerError("Codex 未返回审查结果：" + "\n".join(diagnostics[-5:]))
            # ``--json`` may emit progress and multiple agent_message events.
            # The final agent message is the answer; joining all messages
            # creates invalid ``JSON + JSON`` and causes Extra data errors.
            return texts[-1]
        except subprocess.TimeoutExpired as exc:
            if proc is not None:
                proc.kill()
                proc.wait(timeout=5)
            raise CodexRunnerError("Codex 检查超时") from exc
        except OSError as exc:
            raise CodexRunnerError(str(exc)) from exc
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
