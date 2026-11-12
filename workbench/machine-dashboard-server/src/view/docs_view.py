from pathlib import Path
"""文档页面接口预留。"""
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'web/pages/logs'
logger = get_logger('docs', DEBUG_LOG_DIR)


logger.info('view module loaded; no routes registered yet')



