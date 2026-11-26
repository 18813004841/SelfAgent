import subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from project37.unity_session import UnitySession

class UnitySessionTest(unittest.TestCase):
    def test_compile_success_force_closes_after_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=UnitySession.__new__(UnitySession)
            session.jobdir=Path(tmp)
            session.process=Mock()
            session.process.poll.return_value=None
            session.process.wait.side_effect=[subprocess.TimeoutExpired('Unity',60), 1]
            (session.jobdir/'compile.result').write_text('ok',encoding='utf-8')
            self.assertTrue(session.wait_compile())
            session.process.kill.assert_called_once()
            self.assertEqual(session.process.wait.call_count,2)

    def test_force_close_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=UnitySession.__new__(UnitySession)
            session.jobdir=Path(tmp)
            session.process=Mock()
            session.process.poll.return_value=None
            session.process.wait.side_effect=[subprocess.TimeoutExpired('Unity',60), subprocess.TimeoutExpired('Unity',10)]
            (session.jobdir/'compile.result').write_text('ok',encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'强制关闭失败'):
                session.wait_compile()

    def test_compilation_failure_never_counts_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=UnitySession.__new__(UnitySession)
            session.jobdir=Path(tmp)
            session.process=Mock()
            (session.jobdir/'compile.result').write_text('failed',encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'Unity 编译失败'):
                session.wait_compile()
            session.process.kill.assert_not_called()

    def test_project_already_open_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            session=UnitySession.__new__(UnitySession)
            session.jobdir=Path(tmp)
            session.game=Path(tmp)/'Game'
            session.process=Mock(returncode=1073741845)
            session.process.poll.return_value=1073741845
            (session.jobdir/'unity.log').write_text('It looks like another Unity instance is running with this project open.',encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, '工程已被其他 Unity 实例打开'):
                session._wait('ready',1)

if __name__=='__main__': unittest.main()
