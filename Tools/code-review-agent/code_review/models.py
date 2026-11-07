from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def format_elapsed_time(seconds: float | None) -> str | None:
    """Format elapsed seconds for user-facing reports."""
    if seconds is None:
        return None
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, whole_seconds = divmod(remainder, 60)
    return f"{hours}时{minutes:02d}分{whole_seconds:02d}秒"


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
    author: str | None = None
    commit_sha: str | None = None

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
    elapsed_seconds: float | None = None
    project_path: str | None = None
    branch: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "findings": [x.as_dict() for x in self.findings]}

    def as_display_dict(self) -> dict[str, Any]:
        """User-facing report with the configured Chinese field names."""
        return {
            "检查结果": "检查通过" if self.status in {"passed", "skipped"} and not self.findings else f"失败数量：{len(self.findings)}",
            "上次检查节点": self.old_sha,
            "当前检查节点": self.current_sha,
            "更新文件": self.changed_files,
            "问题内容": [{"严重程度": f.severity, "问题描述": f.message, "文件": f.file, "行数": f.line, "修改人姓名": f.author, "提交SHA": f.commit_sha, "规则": f.rule, "建议": f.suggestion, "可信度": f.confidence} for f in self.findings],
            "警告": self.warnings,
            "导出报告": self.report_path,
            "执行时间": self.executed_at,
            "总耗时": format_elapsed_time(self.elapsed_seconds),
            "工程路径": self.project_path,
            "分支": self.branch,
        }
