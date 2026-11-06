from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ReviewConfig
from .pipeline import ReviewPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental Unity C# code review")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--project", required=True); init.add_argument("--branch", default="main"); init.add_argument("--output", default="Tools/code-review-agent/config.json")
    check = sub.add_parser("check"); check.add_argument("--config", required=True)
    args = parser.parse_args()
    if args.command == "init":
        data = json.loads(Path(__file__).resolve().parents[1].joinpath("config.example.json").read_text(encoding="utf-8")); data["project"].update(path=str(Path(args.project).resolve()), branch=args.branch); Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"); print(args.output); return 0
    result = ReviewPipeline(ReviewConfig.load(Path(args.config))).run(); print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2)); return 0 if result.status in {"passed", "skipped"} else 1


if __name__ == "__main__": raise SystemExit(main())
