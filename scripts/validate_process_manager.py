"""验证工作台进程管理只操作已登记句柄，并能识别启动后立即退出。"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench" / "machine-dashboard-server" / "src"))

from process_manager import ProcessManager, ProcessHandle, ProcessStatus  # noqa: E402
from process_manager.contracts import ManagedProcess  # noqa: E402
import process_manager.manager as manager_module  # noqa: E402


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


manager_module.get_operation_logger = lambda: _Logger()


class FakeProcess(ManagedProcess):
    name = "fake"

    def __init__(self, running: bool = True, exits_on_start: bool = False):
        self.running = running
        self.exits_on_start = exits_on_start
        self.stopped: list[int] = []

    def start(self):
        self.running = not self.exits_on_start
        return ProcessHandle(os.getpid(), 0)

    def stop(self, handle=None):
        if handle and handle.pid:
            self.stopped.append(handle.pid)
        self.running = False

    def is_running(self, handle=None):
        return self.running


def main():
    process = FakeProcess()
    manager = ProcessManager()
    manager.register(process)
    assert manager.cleanup("fake") == []
    assert process.stopped == []
    handle = manager.start("fake")
    assert handle.pid == os.getpid() and manager.status("fake") == ProcessStatus.RUNNING
    assert manager.cleanup("fake") == [os.getpid()]
    assert process.stopped == [os.getpid()]

    crashed = FakeProcess(running=False, exits_on_start=True)
    crashed.name = "crashed"
    manager.register(crashed)
    manager.start("crashed")
    assert manager.status("crashed") == ProcessStatus.FAILED
    restartable = FakeProcess()
    restartable.name = "restartable"
    manager.register(restartable)
    manager.start("restartable")
    assert manager.restart("restartable").pid == os.getpid()
    # 使用真实子进程验证 launcher 启动后立即崩溃的检测路径。
    from process_manager.adapters.scheduler_process import SchedulerProcess
    with tempfile.TemporaryDirectory(prefix="selfagent-launcher-") as directory:
        root = Path(directory)
        script = root / "exit_scheduler.py"
        script.write_text("from pathlib import Path\nraise SystemExit(7)\n", encoding="utf-8")
        real = SchedulerProcess(script, root / "scheduler.pid")
        # Adapter 名称固定为 scheduler，直接调用其真实启动/存活判断。
        handle = real.start()
        import time
        time.sleep(0.2)
        assert not real.is_running(handle)
    print("process manager ownership and crash detection passed")


if __name__ == "__main__":
    main()
