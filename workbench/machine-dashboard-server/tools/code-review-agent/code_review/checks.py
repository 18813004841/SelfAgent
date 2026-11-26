from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

LOCAL_CHECKERS = {
    "runtime-editor-boundary": {
        "name": "UnityEditor Runtime 边界检查",
        "keywords": ("unityeditor", "editor assembly", "editor 目录", "editor目录"),
    },
    "unity-api-misuse": {"name": "Unity API 使用检查", "keywords": ("getcomponent", "gameobject.find", "comparetag", "instantiate", "destroy")},
    "hot-path-performance": {"name": "Unity 热路径性能检查", "keywords": ("update", "fixedupdate", "lateupdate", "linq", "gc", "allocation")},
    "comment-hygiene": {"name": "注释卫生检查", "keywords": ("comment", "todo", "fixme", "commented-out")},
    "naming-conventions": {"name": "C# 命名规范检查", "keywords": ("naming", "pascalcase", "camelcase", "boolean")},
}


def classify_skill_rules(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify each Skill clause against registered deterministic checkers."""
    result = []
    for rule in rules:
        clauses = split_skill_clauses(str(rule.get("content") or ""))
        for index, clause in enumerate(clauses, 1):
            text = clause.lower()
            matched = [
                {"id": checker_id, "name": spec["name"]}
                for checker_id, spec in LOCAL_CHECKERS.items()
                if any(keyword in text for keyword in spec["keywords"])
            ]
            result.append({
                "skill": rule.get("path"),
                "clause": index,
                "title": clause.splitlines()[0][:120],
                "mode": "local_and_model" if matched else "model_only",
                "tools": matched,
                "reason": "本地检查器部分覆盖，完整条款仍交给模型审查" if matched else "暂无本地检查器，交给模型定向审查",
            })
    return result


def split_skill_clauses(content: str) -> list[str]:
    """Split a Skill into reviewable clauses without changing its text."""
    lines = content.splitlines()
    clauses: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if re.match(r"^#{1,4}\s+\S", line) and current:
            clauses.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        clauses.append(current)
    return ["\n".join(item).strip() for item in clauses if "".join(item).strip()]


def model_skill_rules(rules: list[dict[str, Any]], coverage: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return clauses requiring model review, including partial local coverage."""
    by_skill: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        by_skill.setdefault(str(rule.get("path")), []).append(rule)
    result = []
    for item in coverage:
        if item.get("mode") not in {"model_only", "local_and_model"}:
            continue
        source = next(iter(by_skill.get(str(item.get("skill")), [])), None)
        clauses = split_skill_clauses(str(source.get("content") or "")) if source else []
        index = int(item.get("clause") or 1) - 1
        content = clauses[index] if 0 <= index < len(clauses) else ""
        if content:
            result.append({"path": item.get("skill"), "content": content, "clause": item.get("clause")})
    return result


def validate_model_tool_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept only registered checker IDs from a model-generated plan."""
    accepted = []
    for item in plan.get("matches", []):
        if not isinstance(item, dict):
            continue
        checker_id = str(item.get("tool") or "")
        confidence = float(item.get("confidence") or 0)
        if checker_id not in LOCAL_CHECKERS or confidence < 0.8:
            continue
        accepted.append({
            "skill": item.get("skill"),
            "clause": item.get("clause"),
            "title": str(item.get("title") or "")[:120],
            "mode": "local_tool",
            "tools": [{"id": checker_id, "name": LOCAL_CHECKERS[checker_id]["name"]}],
            "reason": "模型辅助匹配，已通过本地白名单校验",
            "confidence": confidence,
        })
    return accepted


def _editor_only_branch(expression: str) -> bool:
    """Return whether a preprocessor expression is guarded by UNITY_EDITOR."""
    normalized = re.sub(r"\s+", "", expression or "")
    return bool(re.fullmatch(r"\(*UNITY_EDITOR\)*(?:&&[^|]+)?", normalized))


def _inside_editor_macro(lines: list[str]) -> list[bool]:
    """Track Unity preprocessor branches so editor-only lines can be excluded."""
    stack: list[dict[str, Any]] = []
    result = []
    for line in lines:
        match = re.match(r"\s*#\s*(if|elif|else|endif)\b(.*)", line)
        inside = bool(stack) and stack[-1]["editor"]
        result.append(inside)
        if not match:
            continue
        kind, expression = match.group(1), match.group(2)
        if kind == "if":
            parent = bool(stack) and stack[-1]["editor"]
            stack.append({"parent": parent, "editor": parent or _editor_only_branch(expression), "initial": re.sub(r"\s+", "", expression), "has_elif": False})
        elif kind == "elif" and stack:
            frame = stack[-1]
            frame["editor"] = frame["parent"] or _editor_only_branch(expression)
            frame["has_elif"] = True
        elif kind == "else" and stack:
            frame = stack[-1]
            frame["editor"] = frame["parent"] or (not frame["has_elif"] and frame["initial"] in {"!UNITY_EDITOR", "(!UNITY_EDITOR)"})
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
        for line_no, code in enumerate(_mask_non_code(lines), 1):
            code = code.strip()
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


def _mask_non_code(lines: list[str]) -> list[str]:
    """Mask comments and literals, preserving positions and opening quotes."""
    result = []
    in_block_comment = False
    in_verbatim = False
    token = re.compile(r'//.*|/\*|@"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
    for raw in lines:
        masked = list(raw)
        pos = 0
        while pos < len(raw):
            if in_block_comment:
                end = raw.find("*/", pos)
                stop = len(raw) if end < 0 else end + 2
                masked[pos:stop] = " " * (stop - pos)
                pos = stop
                in_block_comment = end < 0
                continue
            if in_verbatim:
                start = pos
                while pos < len(raw):
                    if raw[pos] == '"':
                        if pos + 1 < len(raw) and raw[pos + 1] == '"':
                            pos += 2
                            continue
                        pos += 1
                        in_verbatim = False
                        break
                    pos += 1
                masked[start:pos] = " " * (pos - start)
                continue
            match = token.search(raw, pos)
            if not match:
                break
            start, end = match.span()
            value = match.group()
            if value.startswith("//"):
                masked[start:] = " " * (len(raw) - start)
                break
            if value == "/*":
                masked[start:end] = "  "
                in_block_comment = True
            elif value == '@"':
                masked[start] = ' '
                in_verbatim = True
            else:
                masked[start + 1:end] = " " * (end - start - 1)
            pos = end
        result.append("".join(masked))
    return result


def _hot_path_lines(lines: list[str]) -> list[bool]:
    """Track the bodies of Unity update methods, excluding comments and strings."""
    result = []
    pending = False
    depth = 0
    for code in _mask_non_code(lines):
        active = depth > 0
        if not active and not pending and re.search(r"\bvoid\s+(?:Update|FixedUpdate|LateUpdate)\s*\(\s*\)", code):
            pending = True
        if pending:
            if ";" in code and "{" not in code:
                pending = False
            elif "{" in code:
                code = code[code.index("{"):]
                depth = 0
                pending = False
                active = True
        if active:
            depth += code.count("{") - code.count("}")
        result.append(active)
        if depth <= 0:
            depth = 0
    return result


def run_local_checkers(root: Path, files: list[str]) -> list[dict[str, Any]]:
    """Run deterministic, conservative checks on changed C# files."""
    findings = []
    for rel in files:
        path = root / rel
        if not path.is_file() or not rel.lower().endswith(".cs"):
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        hot_path = _hot_path_lines(lines)
        masked = _mask_non_code(lines)
        for no, (raw, masked_code) in enumerate(zip(lines, masked), 1):
            code = masked_code.strip()
            if not code:
                if re.search(r"//\s*(TODO|FIXME)\b|/\*.*\b(TODO|FIXME)\b", raw, re.I):
                    findings.append({"source": "local-tool", "severity": "low", "file": rel, "line": no, "rule": "comment-hygiene", "message": "变更代码包含 TODO/FIXME 注释", "suggestion": "完成事项或补充可跟踪的问题链接。"})
                continue
            in_update = hot_path[no - 1]
            if re.search(r"\bGetComponent(?:InChildren|InParent)?\s*<", code) and in_update:
                findings.append({"source": "local-tool", "severity": "medium", "file": rel, "line": no, "rule": "unity-api-misuse", "message": "在 Unity 热路径中调用 GetComponent，可能产生重复查找开销", "suggestion": "在 Awake/Start 缓存组件引用。"})
            if re.search(r"GameObject\.Find\s*\(", code):
                findings.append({"source": "local-tool", "severity": "medium", "file": rel, "line": no, "rule": "unity-api-misuse", "message": "Runtime 使用 GameObject.Find，可能造成运行时查找开销和脆弱依赖", "suggestion": "使用序列化引用、Binder 或现有 Manager。"})
            if re.search(r"\b\w+\.tag\s*==\s*\"", code):
                findings.append({"source": "local-tool", "severity": "low", "file": rel, "line": no, "rule": "unity-api-misuse", "message": "使用 tag 字符串比较，建议使用 CompareTag", "suggestion": "改为 obj.CompareTag(\"Enemy\")。"})
            if in_update and (re.search(r"\.(Select|Where|ToList|ToArray|OrderBy)\s*\(", code) or re.search(r'\+=\s*(?:\$?@?"|@\$")', code)):
                findings.append({"source": "local-tool", "severity": "medium", "file": rel, "line": no, "rule": "hot-path-performance", "message": "Unity 热路径中可能存在 LINQ 或字符串分配", "suggestion": "避免热路径分配，缓存结果或使用无分配实现。"})
            if re.search(r"//\s*(TODO|FIXME)\b|/\*.*\b(TODO|FIXME)\b", raw, re.I):
                findings.append({"source": "local-tool", "severity": "low", "file": rel, "line": no, "rule": "comment-hygiene", "message": "变更代码包含 TODO/FIXME 注释", "suggestion": "完成事项或补充可跟踪的问题链接。"})
            if re.search(r"\b(StartCoroutine|async\s+|\.Subscribe\s*\()", code):
                # This is a candidate signal; model review remains responsible
                # for deciding whether ownership/cancellation is actually wrong.
                continue
            if re.search(r"\b(?:bool|Boolean)\s+[a-zA-Z]+\s*=", code) and re.search(r"\b(is|has|can|should|was|did)[A-Z_]", code) is None:
                findings.append({"source": "local-tool", "severity": "low", "file": rel, "line": no, "rule": "naming-conventions", "message": "布尔变量名可能缺少 is/has/can/should 等问句前缀", "suggestion": "使用 isX、hasX、canX 或 shouldX 命名。"})
    return findings


def run_compile(root: Path, command: str | None, timeout: int = 300) -> dict[str, Any] | None:
    if not command: return None
    p = subprocess.run(command, cwd=root, shell=True, text=True, capture_output=True, timeout=timeout)
    return {"name": "compile", "status": "passed" if p.returncode == 0 else "failed", "returncode": p.returncode, "stdout": p.stdout[-10000:], "stderr": p.stderr[-10000:]}


