"""验证代码检查日志采用用户目录、轮转并保留连续运行内容。"""
import logging
import os
import tempfile
from pathlib import Path

def main():
    with tempfile.TemporaryDirectory(prefix="selfagent-review-log-") as root:
        os.environ["WORKBENCH_CODE_REVIEW_LOG_DIR"] = root
        os.environ["WORKBENCH_CODE_REVIEW_LOG_MAX_BYTES"] = "200"
        os.environ["WORKBENCH_CODE_REVIEW_LOG_BACKUP_COUNT"] = "2"
        import sys
        src = Path(__file__).resolve().parents[1] / "workbench/machine-dashboard-server/tools/code-review-agent"
        sys.path.insert(0, str(src))
        import code_review.pipeline as pipeline
        handler = next(h for h in pipeline.logger.handlers if isinstance(h, logging.handlers.RotatingFileHandler))
        pipeline.logger.info("validation.first")
        pipeline.logger.info("x" * 400)
        handler.flush()
        files = list(Path(root).glob("pipeline.log*"))
        assert files
        assert any("validation.first" in p.read_text(encoding="utf-8") for p in files)
        for item in list(pipeline.logger.handlers):
            item.close()
            pipeline.logger.removeHandler(item)
    print("code review logging validation passed")

if __name__ == "__main__":
    main()
