from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
from .logging import get_logger

@dataclass
class ViewContext:
    request: object
    path: str
    body: dict
    method: str
    legacy: Callable

class ViewRouter:
    def __init__(self):
        self._routes = {"GET": [], "POST": []}

    def route(self, method: str, *patterns: str):
        def deco(fn):
            for pattern in patterns:
                self._routes[method].append((pattern, fn))
            return fn
        return deco

    def dispatch(self, ctx: ViewContext):
        for pattern, fn in self._routes.get(ctx.method, []):
            matches = ctx.path.startswith(pattern[:-1]) if pattern.endswith("*") else ctx.path == pattern
            if matches:
                import sys
                module = sys.modules[fn.__module__]
                loggers = [getattr(module, "logger", None)]
                view_logger = getattr(module, "view_logger", None)
                if view_logger is not None:
                    loggers.append(view_logger)
                loggers = [item for item in loggers if item is not None]
                for logger in loggers:
                    if hasattr(logger, "request"):
                        logger.request(ctx.method, ctx.path)
                    else:
                        logger.log("DEBUG", "request method=%s path=%s", ctx.method, ctx.path)
                try:
                    result = fn(ctx)
                    for logger in loggers:
                        if hasattr(logger, "response"):
                            logger.response("completed")
                        else:
                            logger.log("DEBUG", "request completed method=%s path=%s", ctx.method, ctx.path)
                    return True if result is None else result
                except Exception:
                    import traceback
                    for logger in loggers:
                        if hasattr(logger, "request"):
                            logger.error("view request failed: %s", traceback.format_exc())
                        else:
                            logger.log("DEBUG", "view request failed: %s", traceback.format_exc())
                    raise
        return None



