from __future__ import annotations

from core.Log import AppLogger


def get_operation_logger() -> AppLogger:
    return AppLogger("machine-dashboard.operations", "process_manager")
