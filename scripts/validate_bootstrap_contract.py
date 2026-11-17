"""Validate bootstrap preflight without installing or changing environments."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bootstrap_projects as bootstrap


class BootstrapContract(unittest.TestCase):
    def invoke(self, args):
        with patch('sys.argv', ['bootstrap', *args]), patch.object(bootstrap, 'run') as run:
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    bootstrap.main()
                except SystemExit as exc:
                    return exc.code, run.call_args_list
            return 0, run.call_args_list

    def test_conflicting_options_never_mutate(self):
        for args in (['--frozen', '--no-install'], ['--frozen', '--upgrade']):
            code, calls = self.invoke(args)
            self.assertEqual(code, 2)
            self.assertEqual(calls, [])

    def test_missing_lock_and_unsupported_manifest_never_mutate(self):
        with tempfile.TemporaryDirectory() as temp:
            for manifest in ('pyproject.toml', 'requirements.txt'):
                with patch.object(bootstrap, 'PROJECTS', {'fixture': (Path(temp), manifest)}):
                    code, calls = self.invoke(['--project', 'fixture', '--frozen'])
                    self.assertEqual(code, 2)
                    self.assertEqual(calls, [])

    def test_locked_install_command(self):
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp)
            (project / '.venv').mkdir()
            (project / 'uv.lock').write_text('fixture')
            with patch.object(bootstrap, 'PROJECTS', {'fixture': (project, 'pyproject.toml')}):
                code, calls = self.invoke(['--project', 'fixture', '--frozen'])
            self.assertEqual(code, 0)
            self.assertEqual(calls[0].args, (['uv', 'sync', '--locked'], project))
            self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
