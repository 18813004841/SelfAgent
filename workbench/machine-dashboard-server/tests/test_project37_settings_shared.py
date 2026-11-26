import json
import os
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('LOCAL_WORKBENCH_START_TIMESTAMP', 'test')
from core import storage
from view import router, ViewContext
from project37 import settings
with patch('core.Log.log_helper.get_view_logger', return_value=Mock()), patch('view.logging.get_logger', return_value=Mock()):
    from project37 import workflow
    from view import project37_view


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_patch = patch.object(storage, 'DB_PATH', self.root / 'state.db')
        self.db_patch.start()
        self.root_patch = patch.object(storage, 'USER_ROOT', self.root)
        self.root_patch.start()
        self.logger_patch = patch.object(project37_view, 'logger', Mock())
        self.logger_patch.start()

    def tearDown(self):
        self.logger_patch.stop()
        self.root_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def dispatch(self, method, user_id, body):
        request = SimpleNamespace(current_user={'id': user_id}, send_json=Mock())
        path = '/api/server-maintenance/project37/settings'
        router.dispatch(ViewContext(request, path, body, method, None))
        return request.send_json.call_args.args[1]

    def test_shared_route_and_legacy_fallback(self):
        old = {key: 'old' for key in settings.SETTING_FIELDS}
        with closing(storage.connect()) as db:
            with db:
                db.execute('INSERT INTO project37_settings(user_id,settings_json) VALUES (?,?)', (1, json.dumps(old)))
        self.assertEqual(self.dispatch('GET', 1, {})['settings'], old)
        values = {key: 'new' for key in settings.SETTING_FIELDS}
        self.assertEqual(self.dispatch('POST', 1, values)['settings'], values)
        self.assertEqual(self.dispatch('GET', 2, {})['settings'], values)
        with self.assertRaises(ValueError):
            self.dispatch('POST', 2, {'unity_editor': 4})
        self.assertEqual(self.dispatch('GET', 1, {})['settings'], values)

    def test_editor_app_and_executable_paths(self):
        game = self.root / 'Game'
        (game / 'ProjectSettings').mkdir(parents=True)
        (game / 'ProjectSettings' / 'ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.27f1\n')
        app = self.root / 'Unity.app'
        exe = app / 'Contents' / 'MacOS' / 'Unity'
        exe.parent.mkdir(parents=True)
        exe.touch()
        self.assertEqual(workflow.unity_executable(game, str(app)), exe)
        self.assertEqual(workflow.unity_executable(game, str(exe)), exe)
        windows_exe = self.root / 'Unity.exe'
        windows_exe.touch()
        self.assertEqual(workflow.unity_executable(game, str(windows_exe)), windows_exe)
        with self.assertRaisesRegex(RuntimeError, '未找到 Unity Editor'):
            workflow.unity_executable(game, str(self.root / 'Missing.app'))


if __name__ == '__main__':
    unittest.main()
