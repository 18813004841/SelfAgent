"""统一日志实例工厂。"""
from functools import lru_cache
from core.settings import get_settings
from .logger import AppLogger

@lru_cache(maxsize=None)
def get_view_logger(name="view"):
    """获取视图日志实例，默认输出到 view.log。"""
    return AppLogger(f"view.{name}", get_settings().view_log_path, debug=True)

@lru_cache(maxsize=None)
def get_default_logger(name="app"):
    return AppLogger(name, get_settings().log_path)

@lru_cache(maxsize=None)
def get_code_review_logger(name="code_review"):
    return AppLogger(f"debug.{name}", get_settings().log_path / "code_review", debug=True)
