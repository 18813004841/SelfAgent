from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


def _editor_only_branch(expression: str) -> bool:
    """Return whether a preprocessor expression is guarded by UNITY_EDITOR."""
    normalized = re.sub(r"\s+", "", expression or "")
    return "UNITY_EDITOR" in normalized and "!UNITY_EDITOR" not in normalized


def _inside_editor_macro(lines: list[str]) -> list[bool]:
    """Track Unity preprocessor branches so editor-only lines can be excluded."""
    stack: list[dict[str, bool]] = []
    result = []
    for line in lines:
        match = re.match(r"\s*#\s*(if|elif|else|endif)\b(.*)", line)
        inside = bool(stack) and stack[-1]["active"] and stack[-1]["editor"]
        result.append(inside)
        if not match:
            continue
        kind, expression = match.group(1), match.group(2)
        if kind == "if":
            parent_active = not stack or stack[-1]["active"]
            editor = _editor_only_branch(expression)
            stack.append({"active": parent_active, "editor": editor, "taken": parent_active, "parent_active": parent_active})
        elif kind == "elif" and stack:
            frame = stack[-1]
            active = frame["parent_active"] and not frame["taken"] if "parent_active" in frame else False
            frame["active"] = active
            frame["editor"] = _editor_only_branch(expression)
            frame["taken"] = frame.get("taken", False) or active
        elif kind == "else" and stack:
            frame = stack[-1]
            parent_active = frame.get("parent_active", True)
            frame["active"] = parent_active and not frame.get("taken", False)
            frame["editor"] = False
            frame["taken"] = True
        elif kind == "endif" and stack:
            stack.pop()
    return result


def unity_runtime_findings(root: Path, files: list[str], markers: list[str]) -> list[dict[str, Any]]:
    findings = []
    for rel in files:
        norm = rel.replace("\\", "/")
        parts = [part.lower() for part in norm.split("/")]
        if not norm.endswith(".cs") or "editor" in parts or norm.lower().endswith("editor.cs"):
            continue
        path = root / rel
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        editor_lines = _inside_editor_macro(lines)
        in_block_comment = False
        for line_no, line in enumerate(lines, 1):
            # Comments must be excluded before marker matching. Keep physical
            # line numbers unchanged so reported locations still point to the
            # source file. This intentionally handles ordinary C# comments;
            # strings are left intact because they can contain valid code text.
            code = line
            if in_block_comment:
                end = code.find("*/")
                if end < 0:
                    continue
                code = code[end + 2:]
                in_block_comment = False
            while True:
                start = code.find("/*")
                if start < 0:
                    break
                end = code.find("*/", start + 2)
                if end < 0:
                    code = code[:start]
                    in_block_comment = True
                    break
                code = code[:start] + code[end + 2:]
            code = re.sub(r"//.*$", "", code).strip()
            if not code:
                continue
            if editor_lines[line_no - 1]:
                continue
            if re.match(r"^\s*#", code):
                continue
            # A bare UnityEditor import is harmless for this boundary check:
            # Unity can remove editor-only imports during player compilation.
            # Report actual editor API/path usage outside an editor macro.
            if re.match(r"^\s*using\s+UnityEditor(?:\s*\.[^;]+)?\s*;", code):
                continue
            if any(marker.lower() in code.lower() for marker in markers):
                findings.append({"source": "unity-rule", "severity": "high", "file": rel, "line": line_no, "rule": "runtime-editor-boundary", "message": "Runtime C# code references Unity Editor code or namespace", "suggestion": "Move editor-only code under an Editor assembly/directory."})
    return findings


def run_compile(root: Path, command: str | None, timeout: int = 300) -> dict[str, Any] | None:
    if not command: return None
    p = subprocess.run(command, cwd=root, shell=True, text=True, capture_output=True, timeout=timeout)
    return {"name": "compile", "status": "passed" if p.returncode == 0 else "failed", "returncode": p.returncode, "stdout": p.stdout[-10000:], "stderr": p.stderr[-10000:]}


