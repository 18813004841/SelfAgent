"""定时任务的通用调度器基类。

任务工具只需要实现业务执行，并通过 ``ScheduleContext`` 上报进度和完成结果；
具体调度器可以在 ``SchedulerBase`` 上扩展参数校验、展示数据和结果转换。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re
from typing import Any, Callable, Mapping

ProgressCallback = Callable[..., None]
FinishCallback = Callable[..., None]
_DAILY_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


@dataclass
class ScheduleContext:
    """一次任务执行的运行时上下文。

    回调由通用调度核心注入。工具不直接操作数据库，只提交业务进度和结果。
    """

    run_id: str
    report_progress: ProgressCallback
    finish: FinishCallback
    metadata: dict[str, Any] = field(default_factory=dict)

    def progress(self, current: int, total: int | None = None, message: str = "", **details: Any) -> None:
        payload: dict[str, Any] = {"current": current, "message": message, "details": details}
        if total is not None:
            payload["total"] = total
        self.report_progress(**payload)

    def complete(self, status: str = "succeeded", result: Any = None, **details: Any) -> None:
        self.finish(status=status, result=result, details=details)


class SchedulerBase(ABC):
    """任务专属调度器的统一接口。

    所有调度器统一为每天一个固定时间点自动执行。子类通过 ``run_at``
    指定 ``HH:MM``，例如 ``"04:00"``。
    """

    tool_id: str
    run_at: str = "04:00"
    schedule_type: str = "daily"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.schedule_type != "daily":
            raise TypeError(f"{cls.__name__} 只能使用每天固定时间调度")
        cls._validate_run_at(cls.run_at)

    @staticmethod
    def _validate_run_at(value: str) -> None:
        if not isinstance(value, str) or not _DAILY_TIME.fullmatch(value):
            raise ValueError(f"执行时间必须是每天的 HH:MM，当前为 {value!r}")

    def schedule_expr(self) -> str:
        """返回每天自动执行的时间点。"""
        self._validate_run_at(self.run_at)
        return self.run_at

    def next_run_at(self, now: float | None = None) -> float:
        """计算下一次每天固定时间点的时间戳。"""
        hour, minute = (int(part) for part in self.schedule_expr().split(":", 1))
        current = datetime.now() if now is None else datetime.fromtimestamp(now)
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
        return candidate.timestamp()

    def validate_args(self, args: Mapping[str, Any]) -> None:
        """校验任务参数；专属调度器可覆盖。"""

    def display_data(self, args: Mapping[str, Any]) -> dict[str, Any]:
        """返回前端展示所需的专属字段。"""
        return {}

    def normalize_result(self, result: Any) -> Any:
        """将工具返回值转换为统一的完成结果。"""
        return result

    @abstractmethod
    def execute(self, args: Mapping[str, Any], context: ScheduleContext) -> Any:
        """执行一次任务；业务进度和完成状态通过 context 上报。"""
        raise NotImplementedError
