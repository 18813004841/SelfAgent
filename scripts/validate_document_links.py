#!/usr/bin/env python3
"""Check relative Markdown links in maintained project documentation."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SKIP_PARTS = {".git", ".venv", ".codex-runtime", "node_modules", ".validation-envs", ".uv-cache-lock"}
DOC_ROOTS = (ROOT / "docs", ROOT / "AiAgent", ROOT / "Tools", ROOT / "workbench", ROOT / "skills")


def iter_docs():
    for base in DOC_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            if not any(part in SKIP_PARTS for part in path.parts):
                yield path


def main() -> int:
    errors: list[str] = []
    checked = 0
    for path in iter_docs():
        checked += 1
        for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for raw in LINK.findall(line):
                target = raw.split("#", 1)[0].strip().strip("<>")
                if not target or target.startswith(("http://", "https://", "mailto:")):
                    continue
                candidate = (path.parent / target).resolve()
                if not candidate.exists():
                    errors.append(f"{path.relative_to(ROOT)}:{line_no}: {raw}")
    if errors:
        print("Broken relative Markdown links:")
        print("\n".join(errors))
        return 1
    print(f"document link validation passed: {checked} Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
