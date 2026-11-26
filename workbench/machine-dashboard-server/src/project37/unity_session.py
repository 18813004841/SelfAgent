"""Owned Unity editor session for the 37 maintenance workflow."""
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

_sessions = {}
_lock = threading.Lock()

class UnitySession:
    def __init__(self, task_id, game, executable, fbs, jobdir):
        self.task_id, self.game, self.jobdir = task_id, Path(game), Path(jobdir)
        self.jobdir.mkdir(parents=True, exist_ok=True)
        self.bridge = self.game / 'Assets' / 'Editor' / ('Project37Session_' + task_id + '.cs')
        if not self.bridge.parent.is_dir() or self.bridge.exists():
            raise RuntimeError('无法安装 Unity 临时会话桥接')
        self.process = None
        try:
            shutil.copyfile(Path(__file__).with_name('Project37SessionBridge.cs'), self.bridge)
            self.process = subprocess.Popen([str(executable), '-batchmode', '-projectPath', str(game), '-logFile', str(self.jobdir / 'unity.log'), '-executeMethod', 'Project37SessionBridge.Start'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=dict(os.environ, KOA_INPUT_FBS_DIR=str(fbs), PROJECT37_SESSION_DIR=str(self.jobdir), PROJECT37_OWNER_PID=str(os.getpid())))
            self._wait('ready', 3600)
        except Exception:
            self.close()
            raise

    def _wait(self, name, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            path = self.jobdir / name
            if path.exists(): return path.read_text(encoding='utf-8', errors='replace')
            if (self.jobdir / 'export.error').exists():
                raise RuntimeError('Unity 导表失败，请查看日志：' + str(self.jobdir / 'unity.log'))
            if self.process.poll() is not None:
                log = self.jobdir / 'unity.log'
                detail = log.read_text(encoding='utf-8', errors='replace') if log.exists() else ''
                if 'another Unity instance is running with this project open' in detail or 'Multiple Unity instances cannot open the same project' in detail:
                    raise RuntimeError('Unity 工程已被其他 Unity 实例打开：' + str(self.game) + '；请关闭占用该工程的 Unity 后重试。日志：' + str(log))
                if 'Failed to launch LicensingClient' in detail:
                    raise RuntimeError('Unity 许可客户端启动失败；请检查编辑器安装及许可证服务。日志：' + str(log))
                raise RuntimeError('Unity 提前退出（退出码 %s），请查看日志：%s' % (self.process.returncode, log))
            time.sleep(.5)
        raise RuntimeError('等待 Unity %s 超时，请查看日志：%s' % (name, self.jobdir / 'unity.log'))

    def request_export(self):
        (self.jobdir / 'export').write_text('start', encoding='utf-8')
        self._wait('export.ok', 3600)

    def wait_compile(self):
        result = self._wait('compile.result', 3600)
        if result.strip() != 'ok':
            errors = self.jobdir / 'compile.errors'
            detail = errors.read_text(encoding='utf-8', errors='replace')[-4000:] if errors.exists() else ''
            raise RuntimeError('Unity 编译失败：' + detail + '；日志：' + str(self.jobdir / 'unity.log'))
        try: code = self.process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            # Only the process started by this session may be forcibly closed.
            code = self.process.poll()
            if code is None:
                try:
                    self.process.kill()
                    self.process.wait(timeout=10)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise RuntimeError('Unity 编译通过，但强制关闭失败，请检查进程；日志：' + str(self.jobdir / 'unity.log')) from exc
                return True
        if code: raise RuntimeError('Unity 编译后退出失败：' + str(code))
        return False

    def close(self):
        if self.process and self.process.poll() is None:
            try:
                (self.jobdir / 'cancel').write_text('cancel', encoding='utf-8')
                self.process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                try: self.process.wait(timeout=10)
                except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
        for path in (self.bridge, Path(str(self.bridge) + '.meta')):
            try: path.unlink(missing_ok=True)
            except OSError: pass

def start(task_id, game, executable, fbs, jobdir):
    session = UnitySession(task_id, game, executable, fbs, jobdir)
    with _lock: _sessions[task_id] = session
    return session

def get(task_id):
    with _lock: session = _sessions.get(task_id)
    if not session or session.process.poll() is not None:
        raise RuntimeError('原 Unity 会话已退出，不能继续，请检查工作区')
    return session

def close(task_id):
    with _lock: session = _sessions.pop(task_id, None)
    if session: session.close()
