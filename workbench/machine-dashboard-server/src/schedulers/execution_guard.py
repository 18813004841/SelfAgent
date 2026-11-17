"""跨进程执行名额：同一任务、同一工程禁止并行。"""
import os
from core.repositories import ReviewExecutionRepository


_REPOSITORY = ReviewExecutionRepository()


def claim(schedule_id, project_path=None):
    return _REPOSITORY.claim(schedule_id, project_path, process_alive=process_alive)


def release(token):
    _REPOSITORY.release(token)


def process_alive(pid):
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.windll.kernel32.GetLastError() == 5
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
