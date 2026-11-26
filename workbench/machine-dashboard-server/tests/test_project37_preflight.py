import sys
import tempfile
import unittest
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from project37.preflight import check

class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        for name in ('project', 'data'):
            remote, repo = self.root / (name + '.git'), self.root / name
            self.git('init', '--bare', str(remote))
            self.git('clone', str(remote), str(repo))
            if name == 'data':
                (repo / 'fbs').mkdir()
                (repo / 'fbs' / 'sample.fbs').write_text('table X {}', encoding='utf-8')
            else:
                (repo / 'test').write_text('test', encoding='utf-8')
            self.git('-C', str(repo), 'add', '.')
            self.git('-C', str(repo), '-c', 'user.name=test', '-c', 'user.email=test@example.test', 'commit', '-m', 'test')
            self.git('-C', str(repo), 'branch', '-M', 'main')
            if name == 'project': self.git('-C', str(repo), 'tag', 'v1')
            self.git('-C', str(repo), 'push', '--tags', 'origin', 'main')
        self.payload = dict(project_path=str(self.root / 'project'), data_path=str(self.root / 'data' / 'fbs'), source_branch='main', new_branch='release/new', tag='v1', data_branch='main')

    def tearDown(self): self.tmp.cleanup()
    @staticmethod
    def git(*args): subprocess.run(['git', *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_valid_and_missing_tag(self):
        self.assertEqual(Path(check(self.payload)['data_root']), self.root / 'data')
        self.payload['tag'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'tag'):
            check(self.payload)

    def test_existing_branch_rejected(self):
        self.payload['new_branch'] = 'main'
        with self.assertRaisesRegex(ValueError, '已存在'):
            check(self.payload)

if __name__ == '__main__': unittest.main()
