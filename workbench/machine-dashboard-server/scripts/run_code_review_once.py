"""Run the configured code-review task once from a stable Windows entrypoint."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
os.environ.setdefault("PYTHONPATH", str(SRC))
os.environ.setdefault("LOCAL_WORKBENCH_START_TIMESTAMP", "manual")
sys.path.insert(0, str(SRC))

from schedulers.code_review_scheduler import CodeReviewScheduler


if __name__ == "__main__":
    CodeReviewScheduler().run_scheduled("6d60e565-f668-4cd4-a293-ab8081fcdb70")
