#!/usr/bin/env python3
"""检查 SelfAgent 的架构文档、入口登记和依赖边界。"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    ROOT / "AGENTS.md",
    ROOT / "docs" / "architecture" / "架构总览.md",
    ROOT / "docs" / "architecture" / "模块边界.md",
    ROOT / "docs" / "architecture" / "架构维护流程.md",
    ROOT / "docs" / "architecture" / "Goal-架构治理计划.md",
    ROOT / "docs" / "architecture" / "入口清单.md",
    ROOT / "docs" / "architecture" / "范围与排除项.md",
    ROOT / "docs" / "architecture" / "依赖矩阵.md",
    ROOT / "docs" / "architecture" / "持续维护.md",
    ROOT / "skills" / "selfagent-architecture" / "SKILL.md",
]
REQUIRED_TERMS = {
    ROOT / "AGENTS.md": ["架构总览", "selfagent-architecture", "工作台"],
    ROOT / "docs" / "architecture" / "架构总览.md": ["workbench/machine-dashboard-server", "Tools/machine-control", "Tools/code-review-agent"],
    ROOT / "skills" / "selfagent-architecture" / "SKILL.md": ["name: selfagent-architecture", "模块边界"],
    ROOT / "docs" / "architecture" / "依赖矩阵.md": ["工作台", "机器控制", "代码检查"],
    ROOT / "docs" / "architecture" / "持续维护.md": ["维护责任", "固定检查", "例外机制"],
}
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w\.]*)", re.MULTILINE)
IGNORED_PARTS = {"__pycache__", ".git", "logs", "tmp-local", "_dbcheck", "_wbcheck", ".uv-cache"}


def iter_files(base: Path, suffix: str):
    for path in base.rglob(f"*{suffix}"):
        if any(part in IGNORED_PARTS for part in path.parts):
            continue
        yield path


def check_documents() -> list[str]:
    errors: list[str] = []
    for path in DOCS:
        if not path.is_file():
            errors.append(f"missing document: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        for term in REQUIRED_TERMS.get(path, []):
            if term not in text:
                errors.append(f"missing required term {term!r}: {path.relative_to(ROOT)}")
        for target in LINK_RE.findall(text):
            if "://" in target or target.startswith("#"):
                continue
            clean = target.split("#", 1)[0].strip()
            if not clean:
                continue
            destination = (path.parent / clean).resolve()
            if not destination.exists():
                errors.append(f"broken link {target!r}: {path.relative_to(ROOT)}")
    return errors


def check_boundaries() -> list[str]:
    errors: list[str] = []
    rules = {
        ROOT / "Tools": {"workbench", "machine_dashboard_server"},
        ROOT / "AiAgent": {"workbench", "machine_dashboard_server"},
    }
    for base, forbidden in rules.items():
        if not base.exists():
            continue
        for path in iter_files(base, ".py"):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError:
                errors.append(f"python file is not utf-8: {path.relative_to(ROOT)}")
                continue
            for match in IMPORT_RE.findall(text):
                root_name = match.split(".", 1)[0]
                if root_name in forbidden:
                    errors.append(f"forbidden import {match}: {path.relative_to(ROOT)}")
    return errors


def check_entry_registration() -> list[str]:
    errors: list[str] = []
    inventory = ROOT / "docs" / "architecture" / "入口清单.md"
    if not inventory.is_file():
        return ["missing document: docs/architecture/入口清单.md"]
    text = inventory.read_text(encoding="utf-8")
    required = [
        "workbench/machine-dashboard-server/src/server.py",
        "Tools/machine-control/server/control_center/server.py",
        "Tools/code-review-agent/code_review/cli.py",
        "AiAgent/AiProject/Codes/Agents/OpenAiAgent/codex_agent/openai_gateway.py",
    ]
    for item in required:
        if item not in text or not (ROOT / item).is_file():
            errors.append(f"entry not registered or missing: {item}")
    return errors


def main() -> int:
    errors = check_documents() + check_boundaries() + check_entry_registration()
    if errors:
        print("architecture check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("architecture check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
