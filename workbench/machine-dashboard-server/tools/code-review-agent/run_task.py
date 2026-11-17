"""Workbench adapter for one scheduled code-review run."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from code_review.config import ReviewConfig
from code_review.pipeline import ReviewPipeline

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--input", default="{}"); args = parser.parse_args()
    options = json.loads(args.input)
    config = ReviewConfig.load(Path(options["config_path"]).resolve() if options.get("config_path") else ROOT / "config.example.json")
    config.raw["project"]["path"] = str(Path(options["project_path"]).resolve())
    if options.get("branch"): config.raw["project"]["branch"] = options["branch"]
    if options.get("skill_paths"): config.raw.setdefault("checks", {})["skill_paths"] = options["skill_paths"]
    config.raw.setdefault("checks", {})["allow_extra_rules"] = bool(options.get("allow_extra_rules"))
    config.raw.setdefault("checks", {})["failure_threshold"] = str(options.get("failure_threshold", "high"))
    result = ReviewPipeline(config).run()
    print(json.dumps(result.as_display_dict(), ensure_ascii=False))
    return 0 if result.status in {"passed", "skipped"} else 1

if __name__ == "__main__": raise SystemExit(main())
