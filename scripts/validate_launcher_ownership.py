"""用真实子进程验证启动器拒绝不匹配句柄并回收持有的进程。"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "workbench/machine-dashboard-server"
sys.path[:0] = [str(ROOT), str(ROOT / "src")]


def main():
    with tempfile.TemporaryDirectory(prefix="selfagent-launcher-") as temp:
        os.environ["LOCALAPPDATA"] = temp
        os.environ["LOCAL_WORKBENCH_START_TIMESTAMP"] = "ownership-validation"
        from launchers.central_server.launcher import CentralServerLauncher
        from launchers.worker_client.launcher import WorkerClientLauncher
        from launchers.scheduler.launcher import SchedulerLauncher
        from launchers.openai_agent.launcher import OpenAIAgentLauncher
        from launchers.local_codex.launcher import LocalCodexLauncher
        from process_manager.contracts import ProcessHandle
        launchers = [
            CentralServerLauncher(Path(temp)),
            WorkerClientLauncher(Path(temp), lambda: temp),
            SchedulerLauncher(Path(temp) / "entry.py", Path(temp) / "scheduler.pid"),
            OpenAIAgentLauncher(Path(temp)),
            LocalCodexLauncher(Path(temp)),
        ]
        try:
            for launcher in launchers:
                proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
                launcher._process = proc
                try:
                    handle = ProcessHandle(proc.pid, 0)
                    assert launcher.is_running(handle)
                    launcher.stop(ProcessHandle(proc.pid + 100000, 0))
                    assert proc.poll() is None, "unmatched handle stopped owned child"
                    launcher.stop(handle)
                    assert proc.poll() is not None
                    assert not launcher.is_running(handle)
                finally:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait(timeout=5)
        finally:
            import logging
            logging.shutdown()
    print("launcher ownership and child reaping validation passed")


if __name__ == "__main__":
    main()
