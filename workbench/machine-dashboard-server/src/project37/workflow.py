"""Project 37 version maintenance task execution."""
import json, os, re, sqlite3, subprocess, sys, threading, time, uuid
from contextlib import closing
from pathlib import Path
from core.storage import connect
from core.settings import get_settings
from core.Log.log_helper import get_view_logger
from .preflight import check, FIELDS

logger = get_view_logger('project37')

def _process_exists(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.GetExitCodeProcess.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # Access denied is not proof of exit.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def recover_interrupted():
    with closing(connect()) as db:
        rows = db.execute("SELECT id,owner_pid,events_json FROM project37_tasks WHERE status IN ('queued','running','pushing')").fetchall()
        for row in rows:
            pid = row['owner_pid']
            if not pid or _process_exists(pid): continue
            events = json.loads(row['events_json'])
            events.append({'time':time.strftime('%H:%M:%S'),'message':'执行进程已退出，任务中断；请检查仓库和 Unity 状态'})
            with db:
                db.execute("UPDATE project37_tasks SET status='failed',events_json=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner_pid=? AND status IN ('queued','running','pushing')", (json.dumps(events,ensure_ascii=False),'执行进程已退出，任务中断',row['id'],pid))


def _can_resume_error(error, events):
    if error.startswith('合并失败'): return True
    messages = [event.get('message', '') for event in events if not event.get('message', '').startswith('执行失败：')]
    return ('超时' in error or error == 'Git 无法启动或超时') and bool(messages) and messages[-1] == '从 tag 创建新分支并合并原分支'


def get_task(user_id, task_id):
    recover_interrupted()
    with closing(connect()) as db:
        row = db.execute('SELECT id,status,events_json,error,conflicts_json,push_state,completed_head FROM project37_tasks WHERE user_id=? AND id=?', (user_id, task_id)).fetchone()
    if not row: raise ValueError('任务不存在')
    events=json.loads(row['events_json'])
    return dict(id=row['id'], status=row['status'], events=events, error=row['error'], conflicts=json.loads(row['conflicts_json']), push_state=row['push_state'], can_resume=row['status']=='paused' or (row['status']=='failed' and _can_resume_error(row['error'],events)), can_push=bool(row['completed_head']) and row['status']=='completed' and row['push_state']!='pushed')

def latest(user_id):
    with closing(connect()) as db:
        row = db.execute('SELECT id FROM project37_tasks WHERE user_id=? ORDER BY rowid DESC LIMIT 1', (user_id,)).fetchone()
    return get_task(user_id, row[0]) if row else None

def update(task_id, status, events, error=''):
    with closing(connect()) as db:
        with db: db.execute('UPDATE project37_tasks SET status=?,events_json=?,error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?', (status,json.dumps(events,ensure_ascii=False),error,task_id))

def create_task(user_id, payload):
    if not isinstance(payload,dict) or any(not isinstance(payload.get(k),str) or not payload[k].strip() or len(payload[k]) > 4096 or '\0' in payload[k] for k in FIELDS):
        raise ValueError('请填写有效的全部维护参数')
    editor = payload.get('unity_editor', '')
    if not isinstance(editor, str) or len(editor) > 4096 or '\0' in editor:
        raise ValueError('Unity 编辑器路径无效')
    params={k:payload[k].strip() for k in FIELDS}
    params['unity_editor'] = editor.strip()
    task_id=uuid.uuid4().hex
    recover_interrupted()
    with closing(connect()) as db:
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute("SELECT 1 FROM project37_tasks WHERE status IN ('queued','running','paused','pushing')").fetchone(): raise RuntimeError('已有37维护任务正在执行或等待处理')
                db.execute('INSERT INTO project37_tasks(id,user_id,status,parameters_json,owner_pid) VALUES(?,?,?,?,?)',(task_id,user_id,'queued',json.dumps(params,ensure_ascii=False),os.getpid()))
        except sqlite3.IntegrityError as exc: raise RuntimeError('已有37维护任务正在执行') from exc
    try: threading.Thread(target=run_task,args=(task_id,params),daemon=True).start()
    except Exception:
        update(task_id,'failed',[],'任务启动失败'); raise
    return get_task(user_id,task_id)

def command(repo,*args,timeout=300,allow_failure=False):
    try:
        p=subprocess.run(['git','-C',str(repo),*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',timeout=timeout,env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_OPTIONAL_LOCKS='0'))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'仓库 {repo} 的 git {args[0]} 超时（{timeout} 秒），请先检查仓库现场') from exc
    except OSError as exc:
        raise RuntimeError(f'仓库 {repo} 的 git {args[0]} 无法启动') from exc
    if p.returncode and not allow_failure:
        output = p.stdout.lower()
        if 'index.lock' in output and ('file exists' in output or 'unable to create' in output):
            reason = 'Git 索引锁已存在，请确认没有 Git 进程运行后处理锁文件'
        elif 'permission denied' in output or 'access is denied' in output:
            reason = '文件访问被拒绝，请检查目录权限和文件占用'
        elif 'unable to unlink' in output or 'cannot unlink' in output:
            reason = '无法删除或替换文件，请检查文件占用和权限'
        else:
            reason = '请检查仓库状态、文件占用及访问权限'
        raise RuntimeError(f'仓库 {repo} 执行 git {args[0]} 失败：{reason}')
    return p

def check_index_lock(repo):
    result = command(repo, 'rev-parse', '--git-path', 'index.lock')
    lock = Path(result.stdout.strip())
    if not lock.is_absolute(): lock = Path(repo) / lock
    if lock.exists():
        raise RuntimeError(f'仓库 {repo} 的 Git 索引锁已存在：{lock.resolve()}；请确认没有 Git 进程运行后处理锁文件')


def unity_executable(game, selected=""):
    version=game/'ProjectSettings'/'ProjectVersion.txt'
    if not version.is_file(): raise RuntimeError('找不到 Unity 项目版本文件')
    match=re.search(r'^m_EditorVersion:\s*([0-9A-Za-z.]+)',version.read_text(encoding='utf-8'),re.M)
    if not match: raise RuntimeError('无法识别 Unity 版本')
    if sys.platform == 'darwin':
        default = Path('/Applications/Unity/Hub/Editor')/match.group(1)/'Unity.app'
    else:
        default = Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'Unity'/'Hub'/'Editor'/match.group(1)/'Editor'/'Unity.exe'
    exe=Path(selected or os.environ.get('PROJECT37_UNITY_EDITOR') or default)
    if exe.suffix.lower() == '.app':
        exe = exe/'Contents'/'MacOS'/'Unity'
    if not exe.is_file(): raise RuntimeError('未找到 Unity Editor：'+str(exe))
    return exe

def record_merge(task_id, project, conflicts):
    base = command(project, 'rev-parse', 'HEAD').stdout.strip()
    merge = command(project, 'rev-parse', 'MERGE_HEAD').stdout.strip()
    with closing(connect()) as db:
        with db:
            db.execute('UPDATE project37_tasks SET conflicts_json=?,base_head=?,merge_head=? WHERE id=?', (json.dumps(conflicts,ensure_ascii=False),base,merge,task_id))


def run_task(task_id,params,resume=False):
    from .conflicts import unmerged, resolve_tag_side
    from . import unity_session
    with closing(connect()) as db:
        row = db.execute('SELECT events_json,conflicts_json,base_head,merge_head FROM project37_tasks WHERE id=?',(task_id,)).fetchone()
    events=json.loads(row['events_json']) if resume else []
    session=None; keep_session=False
    def emit(message):
        events.append({'time':time.strftime('%H:%M:%S'),'message':message}); update(task_id,'running',events)
        logger.info('project37.step task_id=%s step=%s',task_id,message)
    try:
        if resume:
            from .preflight import root
            project=root(params['project_path'], '37工程'); data=root(params['data_path'], '37data工程')
            fbs=data/'fbs'; game=project/'Game'
            session=unity_session.get(task_id)
            branch=command(project,'branch','--show-current').stdout.strip()
            base=command(project,'rev-parse','HEAD').stdout.strip()
            merge=command(project,'rev-parse','MERGE_HEAD',allow_failure=True)
            if resume == 'timeout':
                data_branch=command(data,'branch','--show-current').stdout.strip()
                data_head=command(data,'rev-parse','HEAD').stdout.strip()
                data_expected=command(data,'rev-parse','refs/remotes/origin/'+params['data_branch']+'^{commit}').stdout.strip()
                if data_branch != params['data_branch'] or data_head != data_expected or command(data,'status','--porcelain=v1','-uno',timeout=3600).stdout.strip():
                    raise RuntimeError('37data 分支、提交或工作区已变化，不能继续')
                if not fbs.is_dir() or not any(fbs.glob('*.fbs')):
                    raise RuntimeError('37data 的 fbs 目录不存在或为空，不能继续')
                tag=command(project,'rev-parse','refs/tags/'+params['tag']+'^{commit}').stdout.strip()
                source=command(project,'rev-parse','refs/remotes/origin/'+params['source_branch']+'^{commit}').stdout.strip()
                if branch != params['new_branch']:
                    raise RuntimeError('当前分支与任务不匹配，不能继续')
                if not merge.returncode:
                    if base != tag or merge.stdout.strip() != source:
                        raise RuntimeError('未完成的合并与任务不匹配，不能继续')
                    conflicts=unmerged(project)
                    if not conflicts:
                        raise RuntimeError('合并尚未产生可接续的冲突，请检查仓库现场')
                    record_merge(task_id,project,sorted(conflicts))
                    resolve_tag_side(project,conflicts)
                    remaining=unmerged(project)
                    if remaining:
                        events.append({'time':time.strftime('%H:%M:%S'),'message':f'仍有 {len(remaining)} 个文件冲突，请处理并暂存后继续'})
                        update(task_id,'paused',events)
                        keep_session=True
                        return
                    emit('冲突已按 tag 内容处理，提交合并')
                    command(project,'commit','--no-edit',timeout=3600)
                else:
                    parents=command(project,'show','-s','--format=%P','HEAD').stdout.split()
                    if parents != [tag,source]:
                        raise RuntimeError('合并提交与任务的 tag 或原分支不匹配，不能继续')
                    if command(project,'status','--porcelain=v1','-uno',timeout=3600).stdout.strip():
                        raise RuntimeError('合并后工作区存在已跟踪文件改动，不能继续')
                    emit('已核验合并提交和工作区，继续导表')
            elif resume == 'legacy':
                tag=command(project,'rev-parse','refs/tags/'+params['tag']+'^{commit}').stdout.strip()
                source=command(project,'rev-parse','refs/remotes/origin/'+params['source_branch']+'^{commit}').stdout.strip()
                if branch != params['new_branch'] or base != tag or merge.returncode or merge.stdout.strip() != source:
                    raise RuntimeError('历史任务合并现场与参数不匹配，不能继续')
                conflicts=unmerged(project)
                if not conflicts: raise RuntimeError('历史任务没有可接续的冲突')
                record_merge(task_id,project,sorted(conflicts))
                resolve_tag_side(project,conflicts)
            elif branch != params['new_branch'] or base != row['base_head'] or merge.returncode or merge.stdout.strip() != row['merge_head']:
                raise RuntimeError('合并现场已变化，不能继续，请检查当前分支和合并状态')
            if resume != 'timeout':
                remaining=unmerged(project)
                if remaining:
                    events.append({'time':time.strftime('%H:%M:%S'),'message':f'仍有 {len(remaining)} 个文件冲突，请处理并暂存后继续'})
                    update(task_id,'paused',events)
                    keep_session=True
                    return
                emit('管理员已处理所有冲突，提交合并')
                command(project,'commit','--no-edit',timeout=3600)
        else:
            emit('预检：检查仓库、远端分支和 tag')
            paths=check(params); project=Path(paths['project_root']); data=Path(paths['data_root']); fbs=Path(paths['fbs_path']); game=project/'Game'
            unity_executable(game,params.get('unity_editor',''))
            for key in ('user.name','user.email'):
                if not command(project,'config','--get',key,allow_failure=True).stdout.strip(): raise RuntimeError('Git 提交身份未配置：'+key)
            for repo in (project, data): check_index_lock(repo)
            emit('获取远端分支和 tag')
            for repo,branch in ((project,params['source_branch']),(data,params['data_branch'])):
                command(repo,'fetch','--no-tags','origin',f'+refs/heads/{branch}:refs/remotes/origin/{branch}',timeout=600)
            command(project,'fetch','--no-tags','origin',f"+refs/tags/{params['tag']}:refs/tags/{params['tag']}",timeout=600)
            if command(project,'show-ref','--verify','--quiet','refs/heads/'+params['new_branch'],allow_failure=True).returncode==0: raise RuntimeError('新分支已存在')
            emit('清理并更新两个仓库')
            for repo,branch in ((project,params['source_branch']),(data,params['data_branch'])):
                emit('清理仓库：'+str(repo))
                command(repo,'reset','--hard','HEAD'); command(repo,'clean','-fd')
                command(repo,'checkout','--','.')
                command(repo,'checkout','-B',branch,'refs/remotes/origin/'+branch)
                command(repo,'reset','--hard','refs/remotes/origin/'+branch)
            if not fbs.is_dir() or not any(fbs.glob('*.fbs')): raise RuntimeError('切换后 fbs 目录为空或不存在')
            emit('从 tag 创建新分支并合并原分支')
            command(project,'checkout','-b',params['new_branch'],'refs/tags/'+params['tag'],timeout=3600)
            exe=unity_executable(game,params.get('unity_editor',''))
            jobdir=get_settings().output_dir/'project37'/task_id
            emit('启动 Unity，等待项目加载并暂停自动刷新')
            session=unity_session.start(task_id,game,exe,fbs,jobdir)
            emit('Unity 就绪，清理启动产生的工程改动（保持暂停刷新和编译）')
            bridge = 'Game/Assets/Editor/Project37Session_' + task_id + '.cs'
            command(project,'reset','--hard','HEAD',timeout=3600)
            command(project,'clean','-fd','-e','/'+bridge,'-e','/'+bridge+'.meta',timeout=3600)
            command(project,'checkout','--','.',timeout=3600)
            session=unity_session.get(task_id)
            emit('Unity 就绪，开始合并原分支')
            result=command(project,'merge','--no-edit','--no-ff','refs/remotes/origin/'+params['source_branch'],allow_failure=True,timeout=3600)
            if result.returncode:
                conflicts=unmerged(project)
                if not conflicts: raise RuntimeError('合并失败，但未发现可处理的冲突，请检查工作区')
                record_merge(task_id,project,sorted(conflicts))
                protected=resolve_tag_side(project,conflicts)
                if protected:
                    events.append({'time':time.strftime('%H:%M:%S'),'message':f'Game/BuildFolder 有 {len(protected)} 个冲突，请管理员处理并暂存后继续'})
                    update(task_id,'paused',events)
                    keep_session=True
                    return
                if unmerged(project): raise RuntimeError('自动处理后仍有冲突，请检查工作区')
                command(project,'commit','--no-edit',timeout=3600)
                emit('冲突已按 tag 内容处理并提交合并')
        if session is None:
            raise RuntimeError('缺少合并前启动的 Unity 会话，无法继续导表')
        emit('开始导表；完成后恢复刷新并启动 Unity 编译')
        session.request_export()
        emit('导表完成，提交生成文件')
        command(project,'add','-A','--','Game/Assets/_Script/ConfigGenFB','Game/Assets/_Script/ConfigGen',
                'Game/FlatBuffers_Gen_CS_Temp/ConfigGenFB','Game/FlatBuffers_Gen_CS_Temp/ConfigGen')
        diff = command(project,'diff','--cached','--quiet',allow_failure=True).returncode
        if diff == 1: command(project,'commit','-m','Generate FlatBuffers configuration')
        elif diff == 0: emit('导表无文件变化，无需提交')
        else: raise RuntimeError('无法检查导表生成文件')
        emit('等待 Unity 编译结束')
        forced_close = session.wait_compile()
        emit('Unity 编译通过')
        if forced_close is True:
            emit('Unity 正常退出超时，已强制关闭；请查看 Unity 日志')
        head=command(project,'rev-parse','HEAD').stdout.strip()
        with closing(connect()) as db:
            with db: db.execute('UPDATE project37_tasks SET completed_head=? WHERE id=?',(head,task_id))
        events.append({'time':time.strftime('%H:%M:%S'),'message':'编译通过，Unity 已退出；任务完成（未推送）'}); update(task_id,'completed',events)
    except Exception as exc:
        error=str(exc); events.append({'time':time.strftime('%H:%M:%S'),'message':'执行失败：'+error}); update(task_id,'failed',events,error)
        logger.error('project37.task.failed task_id=%s error_type=%s',task_id,type(exc).__name__)
    finally:
        if not keep_session:
            unity_session.close(task_id)


def resume_task(user_id, task_id):
    with closing(connect()) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM project37_tasks WHERE id=? AND user_id=?',(task_id,user_id)).fetchone()
            if not row: raise ValueError('任务不存在')
            legacy = row['status']=='failed' and _can_resume_error(row['error'],json.loads(row['events_json']))
            timeout_resume = legacy and not row['error'].startswith('合并失败')
            if row['status'] != 'paused' and not legacy: raise RuntimeError('任务不处于可继续状态')
            if db.execute("SELECT 1 FROM project37_tasks WHERE id<>? AND status IN ('queued','running','paused','pushing')",(task_id,)).fetchone(): raise RuntimeError('已有其他维护任务正在执行或等待处理')
            db.execute("UPDATE project37_tasks SET status='running',owner_pid=?,error='' WHERE id=?",(os.getpid(),task_id))
            params=json.loads(row['parameters_json'])
    try:
        threading.Thread(target=run_task,args=(task_id,params,'timeout' if timeout_resume else ('legacy' if legacy else True)),daemon=True).start()
    except Exception:
        update(task_id,'paused',json.loads(row['events_json']),'继续任务启动失败')
        raise
    return get_task(user_id,task_id)


def _push_task(task_id, params, head, events):
    try:
        from .preflight import root
        project=root(params['project_path'],'37工程')
        branch=command(project,'branch','--show-current').stdout.strip()
        current=command(project,'rev-parse','HEAD').stdout.strip()
        if branch != params['new_branch'] or current != head: raise RuntimeError('当前分支或提交已变化，不能推送')
        ref='refs/heads/'+branch
        remote=command(project,'ls-remote','--exit-code','origin',ref,allow_failure=True,timeout=45)
        if remote.returncode not in (0,2): raise RuntimeError('无法检查远端分支')
        if remote.returncode == 0: raise RuntimeError('远端分支已存在，拒绝覆盖')
        command(project,'push','origin',f'{head}:{ref}',timeout=600)
        events.append({'time':time.strftime('%H:%M:%S'),'message':'推送成功：'+ref})
        state='pushed'
    except Exception as exc:
        events.append({'time':time.strftime('%H:%M:%S'),'message':'推送失败：'+str(exc)})
        state='failed'
    with closing(connect()) as db:
        with db: db.execute("UPDATE project37_tasks SET status='completed',push_state=?,events_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(state,json.dumps(events,ensure_ascii=False),task_id))


def push_task(user_id, task_id):
    with closing(connect()) as db:
        with db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM project37_tasks WHERE id=? AND user_id=?',(task_id,user_id)).fetchone()
            if not row: raise ValueError('任务不存在')
            if row['status'] != 'completed' or not row['completed_head'] or row['push_state']=='pushed': raise RuntimeError('只有成功且尚未推送的任务可以推送')
            if db.execute("SELECT 1 FROM project37_tasks WHERE id<>? AND status IN ('queued','running','paused','pushing')",(task_id,)).fetchone(): raise RuntimeError('已有其他维护任务正在执行或等待处理')
            db.execute("UPDATE project37_tasks SET status='pushing',owner_pid=? WHERE id=?",(os.getpid(),task_id))
            params=json.loads(row['parameters_json']); events=json.loads(row['events_json']); head=row['completed_head']
    try: threading.Thread(target=_push_task,args=(task_id,params,head,events),daemon=True).start()
    except Exception:
        with closing(connect()) as db:
            with db: db.execute("UPDATE project37_tasks SET status='completed',push_state='failed' WHERE id=?",(task_id,))
        raise
    return get_task(user_id,task_id)
