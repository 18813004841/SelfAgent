#!/usr/bin/env python3
"""检查 SelfAgent 的架构文档、入口登记和依赖边界。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    ROOT / "AGENTS.md",
    ROOT / "workbench" / "AGENTS.md",
    ROOT / "workbench" / "machine-dashboard-client" / "AGENTS.md",
    ROOT / "workbench" / "machine-dashboard-client" / "WORKBENCH_CLIENT_RULES.md",
    ROOT / "AiAgent" / "AGENTS.md",
    ROOT / "Tools" / "machine-control" / "AGENTS.md",
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
    ROOT / "workbench" / "AGENTS.md": ["HTTP API", "LocalWorkbench"],
    ROOT / "workbench" / "machine-dashboard-client" / "AGENTS.md": ["local_agent.py", "machine-dashboard-server", "127.0.0.1:18991"],
    ROOT / "workbench" / "machine-dashboard-client" / "WORKBENCH_CLIENT_RULES.md": ["18991", "machine-dashboard-server", "Codex"],
    ROOT / "AiAgent" / "AGENTS.md": ["独立管理", "HTTP、CLI"],
    ROOT / "Tools" / "machine-control" / "AGENTS.md": ["中央服务", "Worker"],
    ROOT / "docs" / "architecture" / "架构总览.md": ["workbench/machine-dashboard-server", "Tools/machine-control", "workbench/machine-dashboard-server/tools/code-review-agent"],
    ROOT / "skills" / "selfagent-architecture" / "SKILL.md": ["name: selfagent-architecture", "模块边界"],
    ROOT / "docs" / "architecture" / "依赖矩阵.md": ["工作台", "机器控制", "代码检查"],
    ROOT / "docs" / "architecture" / "持续维护.md": ["维护责任", "固定检查", "例外机制"],
}
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w\.]*)", re.MULTILINE)
IGNORED_PARTS = {"__pycache__", ".git", "logs", "tmp-local", "_dbcheck", "_wbcheck", ".uv-cache", ".venv", "node_modules", ".codex-runtime"}


def is_runtime_artifact(name: str) -> bool:
    """只按路径分类，不读取可能含敏感信息的文件内容。"""
    path = Path(name)
    return bool(
        {"__pycache__", ".venv", ".codex-runtime"}.intersection(path.parts)
        or path.suffix.lower() in {".pyc", ".pyo", ".log", ".db", ".sqlite"}
        or name.endswith((".sqlite-wal", ".sqlite-shm", ".local.json"))
        or name.startswith("Tools/machine-control/packages/") and name.endswith(".zip")
    )


def check_tracked_artifacts() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True,
    )
    names = result.stdout.decode("utf-8").split("\0")
    return [f"tracked runtime artifact: {name}" for name in names if name and is_runtime_artifact(name)]


def check_tracked_local_config() -> list[str]:
    """Flag tracked dotenv files without reading their contents."""
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    names = result.stdout.decode("utf-8").split("\0")
    findings = []
    for name in names:
        path = Path(name)
        if any(part in {".git", ".venv", "node_modules"} for part in path.parts):
            continue
        if path.name.startswith(".env") and not path.name.endswith((".example", ".sample", ".template")):
            findings.append(f"tracked local config: {name}")
    return findings


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
        ROOT / "Tools" / "machine-control": {"workbench", "machine_dashboard_server"},
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


def check_tools_ownership(root: Path = ROOT) -> list[str]:
    """Tools contains machine-control only; ignored legacy bytecode may remain."""
    errors = []
    tools = root / "Tools"
    if not tools.exists():
        return errors
    for path in tools.rglob("*"):
        relative = path.relative_to(tools)
        if relative.parts[0] == "machine-control" or not path.is_file():
            continue
        if "__pycache__" in relative.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        errors.append(f"business file outside project boundary: {path.relative_to(root)}")
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
        "workbench/machine-dashboard-server/tools/code-review-agent/code_review/cli.py",
        "AiAgent/AiProject/Codes/Agents/OpenAiAgent/codex_agent/openai_gateway.py",
    ]
    for item in required:
        if item not in text or not (ROOT / item).is_file():
            errors.append(f"entry not registered or missing: {item}")
    return errors


def main() -> int:
    errors = check_documents() + check_boundaries() + check_tools_ownership() + check_entry_registration()
    if "--tracked-artifacts" in sys.argv:
        errors += check_tracked_artifacts()
    if "--tracked-local-config" in sys.argv:
        errors += check_tracked_local_config()
    if errors:
        print("architecture check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("architecture check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
