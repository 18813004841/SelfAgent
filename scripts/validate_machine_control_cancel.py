"""Exercise cancellation through a real HTTP center and restart its store."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'Tools/machine-control'
sys.path.insert(0, str(PROJECT / "server"))
from control_mcp.client import ControlCenterClient


def validate_client_wrapper():
    calls = []
    client = ControlCenterClient("http://example.invalid", "token")
    client.request = lambda *args: calls.append(args) or {"ok": True}
    assert client.cancel_task("task-wrapper") == {"ok": True}
    assert calls == [("POST", "/api/tasks/task-wrapper/cancel", {})]


def main():
    validate_client_wrapper()
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    env = os.environ.copy()
    env['PYTHONPATH'] = os.pathsep.join(str(PROJECT / p) for p in ('server', 'shared'))
    python = PROJECT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    base = f'http://127.0.0.1:{port}'

    def request(path, body=None, authenticated=True):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer cancel-validation'
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=2) as response:
            return json.load(response)

    def expect_status(code, path, body=None, authenticated=True):
        try:
            request(path, body, authenticated)
        except urllib.error.HTTPError as exc:
            assert exc.code == code, (exc.code, code)
        else:
            raise AssertionError(f'expected HTTP {code}')

    with tempfile.TemporaryDirectory(prefix='selfagent-cancel-') as temp:
        store = Path(temp) / 'center.json'
        command = [str(python), '-m', 'control_center.server', '--port', str(port), '--host', '127.0.0.1', '--token', 'cancel-validation', '--store', str(store)]
        cancelled_id = None
        for restart in (False, True):
            proc = subprocess.Popen(command, cwd=PROJECT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 10
                while True:
                    if proc.poll() is not None:
                        raise AssertionError('owned center exited before readiness')
                    try:
                        request('/health')
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(.1)
                if restart:
                    assert request(f'/api/tasks/{cancelled_id}')['task']['status'] == 'cancelled'
                    assert request('/api/workers/w/tasks/next')['task'] is None
                    continue
                request('/api/workers/register', {'machine_id': 'w'})
                cancelled_id = request('/api/tasks', {'machine_id': 'w'})['task']['task_id']
                path = f'/api/tasks/{cancelled_id}/cancel'
                expect_status(401, path, {}, False)
                assert request(path, {})['task']['status'] == 'cancelled'
                assert request(path, {})['task']['status'] == 'cancelled'
                assert request('/api/workers/w/tasks/next')['task'] is None
                running_id = request('/api/tasks', {'machine_id': 'w'})['task']['task_id']
                request('/api/workers/w/tasks/next')
                running_cancel = request(f'/api/tasks/{running_id}/cancel', {})
                assert running_cancel['task']['status'] == 'running'
                assert running_cancel['task']['cancel_requested'] is True
                assert request(f'/api/tasks/{running_id}')['task']['status'] == 'running'
                expect_status(400, f'/api/tasks/{running_id}/result', {'status': 'queued'})
                expect_status(400, f'/api/tasks/{running_id}/result', {'status': [], 'result': {}})
                expect_status(400, f'/api/tasks/{running_id}/result', {'status': 'succeeded', 'result': []})
                assert request(f'/api/tasks/{running_id}')['task']['status'] == 'running'
                late = request(f'/api/tasks/{cancelled_id}/result', {'status': 'succeeded', 'result': {'late': True}})
                assert late['task']['status'] == 'cancelled'
                assert request(f'/api/tasks/{running_id}/result', {'status': 'succeeded', 'result': {'first': True}})['task']['status'] == 'succeeded'
                assert request(f'/api/tasks/{running_id}/result', {'status': 'failed', 'result': {'late': True}})['task']['result']['first'] is True
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
    print('HTTP cancellation auth, idempotency, running request and restart persistence passed')


if __name__ == '__main__':
    main()
