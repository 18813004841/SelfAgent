from pathlib import Path
"""任务页面接口预留。任务数据统一从调度接口读取。"""
from . import router
from pathlib import Path
from .logging import get_logger

DEBUG_LOG_DIR = Path(__file__).resolve().parents[2] / 'src/tasks/logs'
logger = get_logger('tasks', DEBUG_LOG_DIR)


logger.info('view module loaded; no routes registered yet')



