from __future__ import annotations

import logging
from pathlib import Path


def get_operation_logger() -> logging.Logger:
    logger = logging.getLogger("machine-dashboard.operations")
    if not logger.handlers:
        log_path = Path(__file__).resolve().parents[2] / "logs" / "operations.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
