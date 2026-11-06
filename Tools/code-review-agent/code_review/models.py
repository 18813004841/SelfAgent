from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Finding:
    source: str
    severity: str
    message: str
    file: str | None = None
    line: int | None = None
    rule: str | None = None
    suggestion: str | None = None
    confidence: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class CheckResult:
    status: str
    old_sha: str | None
    current_sha: str
    changed_files: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    agent_status: str = "not_run"
    report_path: str | None = None
    execution_id: str | None = None
    executed_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "findings": [x.as_dict() for x in self.findings]}
