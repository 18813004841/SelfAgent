import os, sys, tempfile, subprocess, unittest, logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
os.environ.setdefault('LOCAL_WORKBENCH_START_TIMESTAMP', 'test')

class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()
        os.environ['LOCALAPPDATA']=str(self.root/'profile')
        from core import storage, settings
        storage.DB_PATH=self.root/'state'/'tasks.db'; storage.USER_ROOT=self.root/'profile'
        settings.SETTING_PATH=self.root/'config'/'settings.json'; settings.USER_SETTINGS_PATH=self.root/'config'/'server-settings.json'
        os.environ['WORKBENCH_OUTPUT_DIR']=str(self.root/'output'); os.environ['WORKBENCH_LOG_PATH']=str(self.root/'logs')
        from project37 import workflow
        self.workflow=workflow
        from project37 import unity_session
        self.session_module = unity_session
        self.session = MagicMock()
        self.session_start_patch = patch.object(unity_session, 'start', return_value=self.session)
        self.session_get_patch = patch.object(unity_session, 'get', return_value=self.session)
        self.session_close_patch = patch.object(unity_session, 'close')
        self.session_start_patch.start(); self.session_get_patch.start(); self.session_close_patch.start()
        self.log_patch=patch.object(workflow, "logger", MagicMock()); self.log_patch.start()
        for name in ('project','data'):
            repo=self.root/name; remote=self.root/(name+'.git')
            self.git('init','--bare',str(remote)); self.git('clone',str(remote),str(repo))
            self.git('-C',str(repo),'config','user.name','Test'); self.git('-C',str(repo),'config','user.email','test@example.test')
            if name=='data':
                (repo/'fbs').mkdir(); (repo/'fbs'/'a.fbs').write_text('table X {}')
            else:
                game=repo/'Game'; (game/'ProjectSettings').mkdir(parents=True); (game/'ProjectSettings'/'ProjectVersion.txt').write_text('m_EditorVersion: 2022.3.27f1\n')
                (game/'Assets'/'Editor').mkdir(parents=True); (game/'Assets'/'Editor'/'keep.txt').write_text('x')
                conf=game/'Assets'/'FlatBuffers'/'Editor'; conf.mkdir(parents=True); (conf/'FlatBuffersConfig.cs').write_text('GenerateFromCommandLine')
                for folder in ('ConfigGenFB','ConfigGen'):
                    d=game/'Assets'/'_Script'/folder; d.mkdir(parents=True); (d/'config.cs').write_text('old')
                    d=game/'FlatBuffers_Gen_CS_Temp'/folder; d.mkdir(parents=True); (d/'config.cs').write_text('old')
            self.git('-C',str(repo),'add','.'); self.git('-C',str(repo),'commit','-m','base'); self.git('-C',str(repo),'branch','-M','main')
            if name=='project':
                self.git('-C',str(repo),'tag','v1'); (repo/'feature.txt').write_text('feature'); self.git('-C',str(repo),'add','.'); self.git('-C',str(repo),'commit','-m','feature')
            self.git('-C',str(repo),'push','--tags','origin','main')
        self.params=dict(project_path=str(self.root/'project'),data_path=str(self.root/'data'/'fbs'),source_branch='main',new_branch='release/new',tag='v1',data_branch='main')
        with closing_db() as db:
            db.execute("INSERT INTO project37_tasks(id,user_id,status,parameters_json) VALUES ('test',1,'queued','{}')"); db.commit()
    def tearDown(self):
        self.session_start_patch.stop(); self.session_get_patch.stop(); self.session_close_patch.stop(); self.log_patch.stop(); logging.shutdown(); self.tmp.cleanup()
    @staticmethod
    def git(*args): return subprocess.run(['git',*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True).stdout.strip()
    def test_end_to_end_git_with_simulated_unity(self):
        project=self.root/'project'; (project/'untracked.txt').write_text('discard'); (project/'feature.txt').write_text('discard')
        phases=[]
        def start_before_merge(*args):
            self.assertEqual(self.git('-C',str(project),'branch','--show-current'),self.params['new_branch'])
            self.assertEqual(self.git('-C',str(project),'rev-parse','HEAD'),self.git('-C',str(project),'rev-parse','v1^{commit}'))
            (project/'Game'/'Assets'/'Editor'/'keep.txt').write_text('unity change')
            (project/'Game'/'Assets'/'Editor'/'Project37Session_test.cs').write_text('bridge')
            (project/'Game'/'Assets'/'Editor'/'Project37Session_test.cs.meta').write_text('meta')
            (project/'unity-untracked.txt').write_text('discard')
            return self.session
        self.session_module.start.side_effect = start_before_merge
        def unity(game,exe,method,fbs,jobdir,phase):
            phases.append(phase)
            if phase=='export':
                self.assertEqual((game/'Assets'/'Editor'/'keep.txt').read_text(),'x')
                self.assertTrue((game/'Assets'/'Editor'/'Project37Session_test.cs').exists())
                self.assertTrue((game/'Assets'/'Editor'/'Project37Session_test.cs.meta').exists())
                self.assertFalse((project/'unity-untracked.txt').exists())
                (game/'Assets'/'_Script'/'ConfigGenFB'/'config.cs').write_text('generated')
                for folder in ('ConfigGenFB','ConfigGen'):
                    (game/'FlatBuffers_Gen_CS_Temp'/folder/'config.cs').write_text('generated')
        self.session.request_export.side_effect = lambda: unity(project/'Game', None, None, None, None, 'export')
        def compile_with_forced_close():
            unity(project/'Game', None, None, None, None, 'compile')
            return True
        self.session.wait_compile.side_effect = compile_with_forced_close
        commands=[]
        actual_command=self.workflow.command
        def track_command(repo,*args,**kwargs):
            commands.append((Path(repo),args))
            return actual_command(repo,*args,**kwargs)
        with patch.object(self.workflow,'unity_executable',return_value=Path('fake')), patch.object(self.workflow,'command',side_effect=track_command):
            self.workflow.run_task('test',self.params)
        task=self.workflow.get_task(1,'test')
        self.assertEqual(task['status'],'completed',task['error']); self.assertEqual(phases,['export','compile'])
        self.assertTrue(any('已强制关闭' in event['message'] for event in task['events']))
        for repo in (self.root/'project',self.root/'data'):
            calls=[args for path,args in commands if path==repo]
            reset=calls.index(('reset','--hard','HEAD'))
            self.assertEqual(calls[reset+1],('clean','-fd'))
            self.assertEqual(calls[reset+2],('checkout','--','.'))
        self.assertEqual(self.git('-C',str(project),'branch','--show-current'),'release/new')
        self.assertFalse((project/'untracked.txt').exists())
        self.assertEqual((project/'feature.txt').read_text(),'feature')
        self.assertEqual(self.git('-C',str(project),'log','-1','--format=%s'),'Generate FlatBuffers configuration')
        for folder in ('ConfigGenFB','ConfigGen'):
            self.assertEqual(self.git('-C',str(project),'show',f'HEAD:Game/FlatBuffers_Gen_CS_Temp/{folder}/config.cs'),'generated')
        self.assertEqual(self.git('--git-dir',str(self.root/'project.git'),'branch','--list','release/new'),'')
        self.assertEqual(list((project/'Game'/'Assets'/'Editor').glob('Project37Bridge*')),[])
    def test_index_lock_stops_before_cleanup(self):
        project = self.root / 'project'
        dirty = project / 'feature.txt'
        dirty.write_text('must remain')
        lock = project / '.git' / 'index.lock'
        lock.write_text('')
        with patch.object(self.workflow, 'unity_executable', return_value=Path('fake')):
            self.workflow.run_task('test', self.params)
        task = self.workflow.get_task(1, 'test')
        self.assertEqual(task['status'], 'failed')
        self.assertIn('索引锁', task['error'])
        self.assertIn('project', task['error'])
        self.assertEqual(dirty.read_text(), 'must remain')
        self.assertTrue(lock.exists())

    def test_command_reports_locked_repository(self):
        project = self.root / 'project'
        (project / '.git' / 'index.lock').write_text('')
        with self.assertRaisesRegex(RuntimeError, '索引锁'):
            self.workflow.command(project, 'reset', '--hard', 'HEAD')

    def test_merge_conflicts_use_tag_side_and_preserve_buildfolder(self):
        from project37.conflicts import unmerged, resolve_tag_side
        repo = self.root / 'project'
        build = repo / 'Game' / 'BuildFolder'
        build.mkdir()
        (build / 'build.txt').write_text('base')
        (repo / 'conflict.txt').write_text('base')
        (repo / 'deleted.txt').write_text('base')
        self.git('-C', str(repo), 'add', '.')
        self.git('-C', str(repo), 'commit', '-m', 'conflict base')
        self.git('-C', str(repo), 'checkout', '-b', 'source')
        (build / 'build.txt').write_text('source')
        (repo / 'conflict.txt').write_text('source')
        (repo / 'deleted.txt').write_text('source')
        self.git('-C', str(repo), 'add', '.')
        self.git('-C', str(repo), 'commit', '-m', 'source')
        self.git('-C', str(repo), 'checkout', 'main')
        (build / 'build.txt').write_text('tag')
        (repo / 'conflict.txt').write_text('tag')
        (repo / 'deleted.txt').unlink()
        self.git('-C', str(repo), 'add', '-A')
        self.git('-C', str(repo), 'commit', '-m', 'tag side')
        merge = subprocess.run(['git', '-C', str(repo), 'merge', 'source'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(merge.returncode, 0)
        conflicts = unmerged(repo)
        self.assertEqual(len(conflicts), 3)
        protected = resolve_tag_side(repo, conflicts)
        self.assertEqual(protected, ['Game/BuildFolder/build.txt'])
        self.assertEqual((repo / 'conflict.txt').read_text(), 'tag')
        self.assertFalse((repo / 'deleted.txt').exists())
        self.assertEqual(set(unmerged(repo)), set(protected))

    def test_continue_waits_until_conflicts_staged(self):
        from project37.conflicts import unmerged, resolve_tag_side
        repo = self.root / 'project'
        build = repo / 'Game' / 'BuildFolder'
        build.mkdir()
        (build / 'build.txt').write_text('base')
        self.git('-C', str(repo), 'add', '.')
        self.git('-C', str(repo), 'commit', '-m', 'base build')
        self.git('-C', str(repo), 'checkout', '-b', 'other')
        (build / 'build.txt').write_text('source')
        self.git('-C', str(repo), 'add', '.')
        self.git('-C', str(repo), 'commit', '-m', 'other')
        self.git('-C', str(repo), 'checkout', '-b', self.params['new_branch'], 'main')
        (build / 'build.txt').write_text('tag')
        self.git('-C', str(repo), 'add', '.')
        self.git('-C', str(repo), 'commit', '-m', 'tag')
        subprocess.run(['git', '-C', str(repo), 'merge', 'other'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        conflicts=unmerged(repo)
        self.workflow.record_merge('test', repo, sorted(conflicts))
        resolve_tag_side(repo, conflicts)
        with patch.object(self.workflow, 'unity_executable', return_value=Path('fake')):
            self.workflow.run_task('test', self.params, True)
        task=self.workflow.get_task(1,'test')
        self.assertEqual(task['status'],'paused')
        self.session_module.close.assert_not_called()
        self.assertEqual(task['conflicts'],['Game/BuildFolder/build.txt'])
        self.session.request_export.assert_not_called()
        (build/'build.txt').write_text('reviewed')
        self.git('-C',str(repo),'add','Game/BuildFolder/build.txt')
        with patch.object(self.workflow,'unity_executable',return_value=Path('fake')):
            self.workflow.run_task('test',self.params,True)
        self.assertEqual(self.workflow.get_task(1,'test')['status'],'completed')
        self.assertEqual((build/'build.txt').read_text(),'reviewed')

    def test_push_only_exact_successful_commit(self):
        repo=self.root/'project'
        self.git('-C',str(repo),'checkout','-b',self.params['new_branch'])
        head=self.git('-C',str(repo),'rev-parse','HEAD')
        (repo/'feature.txt').write_text('staged change')
        self.git('-C',str(repo),'add','feature.txt')
        (repo/'feature.txt').write_text('unstaged change')
        (repo/'untracked.txt').write_text('untracked change')
        self.workflow._push_task('test',self.params,head,[])
        self.assertEqual(self.git('--git-dir',str(self.root/'project.git'),'rev-parse','refs/heads/'+self.params['new_branch']),head)
        self.assertEqual(self.workflow.get_task(1,'test')['push_state'],'pushed')
        self.assertEqual(self.git('--git-dir',str(self.root/'project.git'),'show',head+':feature.txt'),'feature')
        self.assertEqual((repo/'feature.txt').read_text(),'unstaged change')
        self.assertEqual(self.git('-C',str(repo),'show',':feature.txt'),'staged change')
        self.workflow._push_task('test',self.params,head,[])
        self.assertEqual(self.workflow.get_task(1,'test')['push_state'],'failed')

    def test_resume_timeout_after_completed_merge(self):
        repo=self.root/'project'
        self.git('-C',str(repo),'checkout','-b',self.params['new_branch'],'v1')
        self.git('-C',str(repo),'merge','--no-ff','--no-edit','refs/remotes/origin/main')
        before=self.git('-C',str(repo),'rev-parse','HEAD')
        with patch.object(self.workflow,'unity_executable',return_value=Path('fake')):
            self.workflow.run_task('test',self.params,'timeout')
        task=self.workflow.get_task(1,'test')
        self.assertEqual(task['status'],'completed',task['error'])
        self.assertEqual(self.git('-C',str(repo),'rev-parse','HEAD'),before)
        self.session.request_export.assert_called_once()

    def test_resume_timeout_rejects_changed_worktree(self):
        repo=self.root/'project'
        self.git('-C',str(repo),'checkout','-b',self.params['new_branch'],'v1')
        self.git('-C',str(repo),'merge','--no-ff','--no-edit','refs/remotes/origin/main')
        (repo/'feature.txt').write_text('local changes')
        with patch.object(self.workflow,'unity_executable',return_value=Path('fake')):
            self.workflow.run_task('test',self.params,'timeout')
        self.assertEqual(self.workflow.get_task(1,'test')['status'],'failed')
        self.assertEqual((repo/'feature.txt').read_text(),'local changes')
        self.session.request_export.assert_not_called()

    def test_unity_export_failure_stops(self):
        self.session.request_export.side_effect = RuntimeError('export failed')
        with patch.object(self.workflow,'unity_executable',return_value=Path('fake')):
            self.workflow.run_task('test',self.params)
        self.assertEqual(self.workflow.get_task(1,'test')['status'],'failed'); self.session.request_export.assert_called_once()

def closing_db():
    from contextlib import closing
    from core.storage import connect
    return closing(connect())

if __name__=='__main__': unittest.main()
