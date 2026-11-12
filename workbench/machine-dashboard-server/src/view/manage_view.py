from pathlib import Path
"""管理页面接口。"""
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'src/process_manager/logs'
logger = get_logger('manage', DEBUG_LOG_DIR)


logger.info('view module loaded; no routes registered yet')



