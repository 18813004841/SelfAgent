"""Verify the Worker executor terminates an owned process tree on cancellation."""
import threading
import time
import sys
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools/machine-control/client"))
from control_worker.executor import run_shell  # noqa: E402


def validate_cleanup_failure() -> None:
    if os.name != "nt":
        return
    event = threading.Event()
    event.set()
    root = Mock(pid=123, returncode=0)
    root.poll.return_value = 0
    root.wait.return_value = 0
    denied = subprocess.CompletedProcess([], 1, "", "ERROR: Access denied")
    with patch("control_worker.executor.subprocess.Popen", return_value=root), patch(
        "control_worker.executor.subprocess.run", return_value=denied
    ):
        result = run_shell({"command": "python ignored", "timeout": 60}, cancel_event=event)
    assert result.get("cleanup_error") == "ERROR: Access denied", result
    assert result["ok"] is False


def main() -> None:
    validate_cleanup_failure()
    event = threading.Event()
    result_box = {}
    pid_file = Path(tempfile.gettempdir()) / f"selfagent-worker-child-{os.getpid()}.pid"
    pid_file.unlink(missing_ok=True)
    command = (
        "python -c \"import os,time; "
        f"open(r'{pid_file}', 'w').write(str(os.getpid())); "
        "time.sleep(30)\""
    )
    thread = threading.Thread(target=lambda: result_box.setdefault(
        "result", run_shell({"command": command, "timeout": 60}, cancel_event=event)))
    thread.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not pid_file.exists():
        time.sleep(0.05)
    assert pid_file.exists(), "child process did not start"
    child_pid = int(pid_file.read_text().strip())
    event.set()
    thread.join(timeout=10)
    assert not thread.is_alive(), "executor did not stop after cancellation"
    assert result_box["result"].get("cancelled") is True
    time.sleep(0.5)
    if os.name == "nt":
        probe = subprocess.run(
            ["tasklist", "/FI", f"PID eq {child_pid}"],
            capture_output=True, text=True, check=False,
        )
        assert str(child_pid) not in probe.stdout, f"descendant {child_pid} survived cancellation"
    else:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError(f"descendant {child_pid} survived cancellation")
    pid_file.unlink(missing_ok=True)
    print("worker process cancellation passed")


if __name__ == "__main__":
    main()
