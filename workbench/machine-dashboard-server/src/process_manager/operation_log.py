from __future__ import annotations

import logging
from pathlib import Path


def get_operation_logger() -> logging.Logger:
    logger = logging.getLogger("machine-dashboard.operations")
    if not logger.handlers:
        log_path = Path(__file__).resolve().parents[2] / "logs" / "operations.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        # Keep a stable feature label in every operational log line so the
        # dashboard can filter scheduler/API/process events without parsing
        # free-form text first.
        handler.setFormatter(logging.Formatter("%(asctime)s [feature=machine-dashboard] %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
