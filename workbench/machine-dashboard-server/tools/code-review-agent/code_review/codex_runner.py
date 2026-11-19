from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import sys

SERVER_ROOT = Path(__file__).resolve().parents[3]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))
from integrations.codex_cli import CodexCliClient, CodexCliError


class CodexRunnerError(CodexCliError):
    pass


class CodexRunner:
    """Run the server-local Codex CLI without exposing a model HTTP endpoint."""

    def __init__(self, project: Path, timeout: float = 900, executable: str | None = None,
                 model: str | None = None, sandbox: str = "read-only") -> None:
        self.project = project
        self.client = CodexCliClient(executable=executable, model=model, sandbox=sandbox, timeout=timeout)

    def run(self, prompt: str, cancel: Callable[[], bool] | None = None,
            on_event: Callable[[dict[str, Any]], None] | None = None) -> str:
        try:
            return self.client.execute(prompt, cwd=self.project, cancel=cancel, on_event=on_event).text
        except CodexCliError as exc:
            raise CodexRunnerError(str(exc)) from exc
