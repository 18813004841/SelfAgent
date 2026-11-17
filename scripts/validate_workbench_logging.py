"""验证工作台日志写入配置目录并使用轮转处理器。"""
import os
import logging
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="selfagent-log-") as root:
        os.environ["LOCALAPPDATA"] = root
        os.environ["LOCAL_WORKBENCH_START_TIMESTAMP"] = "validation"
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workbench/machine-dashboard-server/src"))
        from core.Log.logger import AppLogger
        from view.logging import get_logger
        from logging.handlers import RotatingFileHandler
        logger = AppLogger("validation")
        second = AppLogger("validation-second")
        assert logger.runtime.handlers[0] is second.runtime.handlers[0]
        logger.info("validation.event")
        logger.info("token=validation-secret password=validation-password Bearer validation-bearer")
        logger.info("parameterized token=%s count=%s", "parameter-secret", 7)
        try:
            raise ValueError("password=exception-secret")
        except ValueError:
            logger.exception("validation.exception")
        text = logger.log_file.read_text(encoding="utf-8")
        assert "validation-secret" not in text and "validation-password" not in text and "validation-bearer" not in text
        assert "[REDACTED]" in text
        assert "parameter-secret" not in text and "exception-secret" not in text
        assert "count=7" in text and "ValueError" in text and "Traceback" in text
        old = logger.log_dir / "20000101_000000_000000.log"
        old.write_text("old", encoding="utf-8")
        os.utime(old, (0, 0))
        fresh = logger.log_dir / "fresh-session.log"
        fresh.write_text("fresh", encoding="utf-8")
        custom = logger.log_dir / "user-notes.log"
        custom.write_text("keep", encoding="utf-8")
        os.utime(custom, (0, 0))
        os.environ["WORKBENCH_LOG_RETENTION_DAYS"] = "1"
        AppLogger("retention-check")
        assert not old.exists()
        assert fresh.exists()
        assert custom.exists()
        assert isinstance(logger.runtime.handlers[0], RotatingFileHandler)
        assert logger.log_file.is_file()
        assert str(logger.log_file).startswith(str(Path(root) / "LocalWorkbench"))
        view_logger = get_logger("validation-view", Path("source-tree-should-not-be-used"))
        view_logger.info("validation.view.event")
        assert view_logger.debug_log.log_file.is_file()
        assert str(view_logger.debug_log.log_file).startswith(str(Path(root) / "LocalWorkbench"))
        assert "source-tree-should-not-be-used" not in str(view_logger.debug_log.log_file)
        # Close the existing handlers before TemporaryDirectory cleanup so
        # Windows does not retain an open file handle on the validation log.
        for owner in (logger, second):
            for handler in list(owner.runtime.handlers) + list(owner.debugger.handlers):
                handler.close()
                owner.runtime.removeHandler(handler) if handler in owner.runtime.handlers else None
                owner.debugger.removeHandler(handler) if handler in owner.debugger.handlers else None
        os.environ["WORKBENCH_LOG_RETENTION_DAYS"] = "invalid"
        try:
            AppLogger("invalid-retention")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid retention value was accepted")
        for item in logging.Logger.manager.loggerDict.values():
            if isinstance(item, logging.Logger):
                for handler in list(item.handlers):
                    handler.close()
                    item.removeHandler(handler)
        os.environ["WORKBENCH_LOG_RETENTION_DAYS"] = "1"
        for handler in list(logger.runtime.handlers):
            handler.close()
            logger.runtime.removeHandler(handler)
            second.runtime.removeHandler(handler)
        for handler in list(view_logger.view.runtime.handlers) + list(view_logger.view.debugger.handlers) + list(view_logger.debug_log.runtime.handlers) + list(view_logger.debug_log.debugger.handlers):
            handler.close()
            for owner in (view_logger.view, view_logger.debug_log):
                owner.runtime.removeHandler(handler) if handler in owner.runtime.handlers else None
                owner.debugger.removeHandler(handler) if handler in owner.debugger.handlers else None
        for handler in list(logger.debugger.handlers):
            if handler not in logger.runtime.handlers:
                handler.close()
            logger.debugger.removeHandler(handler)
            second.debugger.removeHandler(handler)
        print("workbench logging validation passed")


if __name__ == "__main__":
    main()




