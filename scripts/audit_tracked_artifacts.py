"""列出已被 Git 跟踪的运行产物，不读取文件内容。"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True)
    paths = [Path(item) for item in result.stdout.decode("utf-8", errors="replace").split("\0") if item]
    markers = (".log", ".db", ".sqlite", ".pyc", ".venv", "__pycache__", ".codex-runtime", "/data/", "\\data\\", "/logs/", "\\logs\\", ".zip")
    findings = [p.as_posix() for p in paths if p.name != ".gitkeep" and any(marker in p.as_posix().lower() for marker in markers)]
    print(json.dumps({"count": len(findings), "paths": findings}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
