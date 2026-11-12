from pathlib import Path
"""测试调度页面接口。"""
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'src/schedulers/logs'
logger = get_logger('test_scheduler', DEBUG_LOG_DIR)


logger.info('view module loaded; no routes registered yet')



