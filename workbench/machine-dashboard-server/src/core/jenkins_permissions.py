"""Read and update Jenkins global matrix authorization via its administrator script endpoint."""
import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from core import storage
from core.jenkins import NoRedirect, url_for
from core.settings import get_user_settings_path

# Input is JSON/base64 encoded before embedding; it is never evaluated as Groovy source.
_SCRIPT = r'''
import jenkins.model.Jenkins
import hudson.security.PermissionGroup
import hudson.security.GlobalMatrixAuthorizationStrategy
import hudson.security.ProjectMatrixAuthorizationStrategy
import org.jenkinsci.plugins.matrixauth.AuthorizationType
import org.jenkinsci.plugins.matrixauth.PermissionEntry
import groovy.json.JsonOutput
import groovy.json.JsonSlurperClassic
import java.security.MessageDigest

def input = new JsonSlurperClassic().parseText(new String('__PAYLOAD__'.decodeBase64(), 'UTF-8'))
def j = Jenkins.get()
def response = [:]
synchronized (j) {
  def a = j.authorizationStrategy
  if (!(a.class == GlobalMatrixAuthorizationStrategy || a.class == ProjectMatrixAuthorizationStrategy)) {
    response = [error:'不支持的授权策略：' + a.class.name]
  } else if (!a.metaClass.respondsTo(a, 'getGrantedPermissionEntries')) {
    response = [error:'不支持的矩阵插件版本']
  } else {
    def exists = null
    if (input.action != 'catalog') {
      try { j.securityRealm.loadUserByUsername2(input.username); exists = true }
      catch (org.springframework.security.core.userdetails.UsernameNotFoundException ignored) { exists = false }
      catch (Exception ignored) { exists = null }
    }
    def grants = a.grantedPermissionEntries
    def fingerprint = { m ->
      def lines = []
      m.each { p, entries -> entries.each { e -> lines << (p.id + '\t' + e.type.name() + '\t' + e.sid) } }
      MessageDigest.getInstance('SHA-256').digest(lines.sort().join('\n').getBytes('UTF-8')).encodeHex().toString()
    }
    // Use exactly the groups and visibility rules of this Jenkins matrix descriptor.
    def descriptor = a.descriptor
    if (!descriptor.metaClass.respondsTo(descriptor, 'showPermission', hudson.security.Permission)) throw new IllegalStateException('matrix permission visibility unavailable')
    def permissions = descriptor.allGroups.collectMany { g -> g.permissions.findAll { p -> descriptor.showPermission(p) }.collect { p -> [id:p.id, group:g.title.toString(), name:p.name] } }.sort { it.id }
    def managedIds = permissions.collect { it.id } as Set
    def current = [] as Set
    def ambiguous = false
    if (input.action != 'catalog') grants.each { p, entries -> entries.each { e ->
      if (j.securityRealm.userIdStrategy.equals(e.sid, input.username) && e.type == AuthorizationType.USER && managedIds.contains(p.id)) current.add(p.id)
      if (j.securityRealm.userIdStrategy.equals(e.sid, input.username) && e.type == AuthorizationType.EITHER) ambiguous = true
    } }
    def revision = fingerprint(grants)
    if (input.action == 'save') {
      if (exists != true) response = [error:'无法确认用户已注册，未保存']
      else if (ambiguous) response = [error:'该用户存在类型不明确的旧权限项，请在 Jenkins 中处理']
      else if (j.securityRealm.userIdStrategy.equals(input.username, input.admin)) response = [error:'不能修改当前管理账号的权限']
      else if (revision != input.revision) response = [error:'权限配置已变更，请重新搜索']
      else if (!(input.permissions instanceof List) || !input.permissions.every { id -> permissions.any { it.id == id } }) response = [error:'权限列表无效，请重新搜索']
      else {
        def next = a.class.getDeclaredConstructor().newInstance()
        grants.each { p, entries -> entries.each { e ->
          if (!(e.type == AuthorizationType.USER && j.securityRealm.userIdStrategy.equals(e.sid, input.username) && managedIds.contains(p.id))) next.add(p, e)
        } }
        input.permissions.unique().each { id -> def p = hudson.security.Permission.fromId(id); if (p == null) throw new IllegalArgumentException('permission unavailable'); next.add(p, new PermissionEntry(AuthorizationType.USER, input.username)) }
        j.setAuthorizationStrategy(next)
        j.save()
        response = [saved:true, revision:fingerprint(next.grantedPermissionEntries)]
      }
    } else response = [registered:exists, permissions:permissions, granted:current.sort(), ambiguous:ambiguous, revision:revision]
  }
}
println('WORKBENCH_JSON:' + JsonOutput.toJson(response))
'''


# This probe is compatible with Jenkins 2.144 and does not import newer matrix classes.
# Role permissions remain read-only; editing selects existing global roles on a copied strategy.
# Legacy role SIDs may also match groups, so the UI identifies the shared SID semantics.
_ROLE_PROBE = r'''
import groovy.json.JsonOutput
import groovy.json.JsonSlurperClassic
import hudson.security.PermissionGroup
import java.security.MessageDigest

def input = new JsonSlurperClassic().parseText(new String('__PAYLOAD__'.decodeBase64(), 'UTF-8'))
def j = Jenkins.instance
def result = [roleBased:false]
synchronized (j) {
  def a = j.authorizationStrategy
  if (a.class.name == 'com.michelin.cio.hudson.plugins.rolestrategy.RoleBasedAuthorizationStrategy') {
    def exists = null
    if (input.action != 'catalog') {
      try { j.securityRealm.loadUserByUsername(input.username); exists = true }
      catch (Exception e) { exists = e.class.name.endsWith('UsernameNotFoundException') ? false : null }
    }
    def fingerprint = { strategy -> MessageDigest.getInstance('SHA-256').digest(Jenkins.XSTREAM2.toXML(strategy).getBytes('UTF-8')).encodeHex().toString() }
    def grantsByType = ['globalRoles', 'projectRoles'].collectEntries { type -> [(type):a.getGrantedRoles(type)] }
    def availableRoleIds = grantsByType.collectMany { type, grants -> grants.keySet().collect { type + ':' + it.name } }.sort()
    def grants = grantsByType['globalRoles']
    def matched = []
    def granted = [] as Set
    if (input.action != 'catalog') grants.each { role, sids ->
      if (sids.any { it.equalsIgnoreCase(input.username) }) {
        matched.add(role.name)
        role.permissions.each { granted.add(it.id) }
      }
    }
    def matchedRoleIds = []
    if (input.action != 'catalog') grantsByType.each { type, entries -> entries.each { role, sids -> if (sids.any { it.equalsIgnoreCase(input.username) }) matchedRoleIds.add(type + ':' + role.name) } }
    def revision = fingerprint(a)
    if (input.action == 'save_roles') {
      if (exists != true) result = [error:'无法确认用户已注册，未保存']
      else if (input.username.equalsIgnoreCase(input.admin)) result = [error:'不能修改当前管理账号的角色']
      else if (revision != input.revision) result = [error:'角色配置已变更，请重新搜索']
      else if (!(input.roles instanceof List) || !input.roles.every { availableRoleIds.contains(it) } || (input.roles as Set).size() != input.roles.size()) result = [error:'角色列表无效，请重新搜索']
      else if (j.securityRealm.class.name != 'hudson.security.HudsonPrivateSecurityRealm') result = [error:'当前身份源无法安全区分用户与用户组，请在 Jenkins 中管理角色']
      else if (['authenticated', 'anonymous'].any { it.equalsIgnoreCase(input.username) }) result = [error:'不能修改系统主体角色']
      else {
        def next = Jenkins.XSTREAM2.fromXML(Jenkins.XSTREAM2.toXML(a))
        def field = a.class.getDeclaredField('grantedRoles'); field.accessible = true
        if (next.is(a)) throw new IllegalStateException('cannot copy role map')
        grantsByType.each { type, entries ->
          def roleMap = field.get(next).get(type)
          if (roleMap == null) throw new IllegalStateException('role map missing')
          entries.each { role, sids ->
            def copiedRole = roleMap.getRole(role.name)
            if (copiedRole == null) throw new IllegalStateException('role missing from copy')
            sids.findAll { it.equalsIgnoreCase(input.username) }.each { sid -> roleMap.unAssignRole(copiedRole, sid) }
            if (input.roles.contains(type + ':' + role.name)) roleMap.assignRole(copiedRole, input.username)
          }
        }
        j.setAuthorizationStrategy(next)
        try { j.save() } catch (Exception e) { j.setAuthorizationStrategy(a); throw e }
        result = [roleBased:true, saved:true, revision:fingerprint(next)]
      }
    } else if (input.action == 'save') {
      result = [error:'角色授权模式请使用角色分配操作']
    } else {
      def permissions = PermissionGroup.all.collectMany { g -> g.permissions.findAll { it.enabled }.collect { p -> [id:p.id, group:g.title.toString(), name:p.name] } }.sort { it.id }
      result = [roleBased:true, registered:exists, permissions:permissions, granted:granted.sort(), roles:matched.sort(), availableRoles:availableRoleIds, assignedRoles:matchedRoleIds.sort(), readOnly:true, revision:revision, roleEditable:j.securityRealm.class.name == 'hudson.security.HudsonPrivateSecurityRealm']
    }
  } else if (input.action == 'save_roles') result = [error:'授权策略已变更，请重新搜索']
}
println('WORKBENCH_JSON:' + JsonOutput.toJson(result))
'''


def _credentials():
    path = get_user_settings_path()
    config = {}
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError, json.JSONDecodeError):
            raise ValueError('无法读取 Jenkins 本地配置，请检查配置文件格式和权限') from None
        if not isinstance(config, dict):
            raise ValueError('服务端配置必须为 JSON 对象')
        config = config.get('jenkins_management', {})
        if not isinstance(config, dict):
            raise ValueError('jenkins_management 必须为 JSON 对象')
    user = os.environ.get('JENKINS_MANAGEMENT_USERNAME', config.get('username', 'koa'))
    password = os.environ.get('JENKINS_MANAGEMENT_PASSWORD', config.get('password'))
    if not isinstance(user, str) or not user.strip():
        raise ValueError('Jenkins 管理账号不能为空')
    if not isinstance(password, str) or not password:
        raise ValueError('请填写服务端配置 jenkins_management.password，或设置 JENKINS_MANAGEMENT_PASSWORD')
    return user.strip(), password


def _targets():
    with closing(storage.connect()) as db:
        return {row['ip']: dict(row) for row in db.execute('SELECT ip, scheme, port FROM jenkins_servers')}


def _execute(item, payload):
    user, password = _credentials()
    payload['admin'] = user
    base = url_for(item['ip'], item['scheme'], item['port'])
    auth = base64.b64encode(f'{user}:{password}'.encode()).decode()
    headers = {'Authorization': 'Basic ' + auth}
    opener = urllib.request.build_opener(NoRedirect, urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor())
    try:
        with opener.open(urllib.request.Request(base + 'crumbIssuer/api/json', headers=headers), timeout=5) as response:
            crumb = json.loads(response.read(65536))
        headers[crumb['crumbRequestField']] = crumb['crumb']
        encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()
        def run(script):
            data = urllib.parse.urlencode({'script': script.replace('__PAYLOAD__', encoded)}).encode()
            with opener.open(urllib.request.Request(base + 'scriptText', data=data, headers=headers), timeout=15) as response:
                content = response.read(2 * 1024 * 1024).decode('utf-8', 'replace')
            lines = [line[len('WORKBENCH_JSON:'):] for line in content.splitlines() if line.startswith('WORKBENCH_JSON:')]
            if len(lines) != 1: raise RuntimeError('Jenkins 返回了无法识别的结果')
            result = json.loads(lines[0])
            if result.get('error'): raise RuntimeError(result['error'])
            return result
        probe = run(_ROLE_PROBE)
        return probe if probe.get('roleBased') else run(_SCRIPT)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403): raise RuntimeError('Jenkins 认证失败或账号无管理员权限') from None
        raise RuntimeError(f'Jenkins 返回 HTTP {exc.code}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('无法连接 Jenkins 或请求超时') from None
    except (KeyError, ValueError):
        raise RuntimeError('Jenkins 返回了无法识别的结果') from None


def _username(body):
    name = body.get('username')
    if not isinstance(name, str) or not name.strip() or len(name) > 128: raise ValueError('请输入有效用户名')
    return name.strip()


def _read_results(username=None):
    targets = _targets()
    with closing(storage.connect()) as db:
        profiles_by_ip = {r['ip']: {'strategy':r['strategy'], 'profiles':json.loads(r['profiles_json']), 'revision':hashlib.sha256(r['profiles_json'].encode('utf-8')).hexdigest()} for r in db.execute('SELECT ip, strategy, profiles_json FROM jenkins_permission_profiles')}
    def read(pair):
        ip, item = pair
        try:
            payload = {'action':'search', 'username':username} if username is not None else {'action':'catalog'}
            return {'ip': ip, **_execute(item, payload), 'profileConfig':profiles_by_ip.get(ip)}
        except (RuntimeError, ValueError) as exc: return {'ip': ip, 'error': str(exc)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(read, targets.items()))



def search(body):
    return _read_results(_username(body))


def catalog():
    return _read_results()

def profiles(body):
    ip = body.get('ip')
    target = _targets().get(ip)
    if not target: raise ValueError('Jenkins 不存在，请重新搜索')
    data = body.get('profiles')
    if not isinstance(data, dict) or set(data) != {'qa', 'admin'}: raise ValueError('权限方案无效')
    current = _execute(target, {'action':'catalog'})
    if current.get('revision') != body.get('revision'): raise ValueError('Jenkins 权限配置已变更，请重新搜索')
    strategy = 'roles' if current.get('roleBased') else 'matrix'
    if strategy == 'roles' and not current.get('roleEditable'): raise ValueError('此身份源不支持修改角色')
    allowed = set(current.get('availableRoles', [])) if strategy == 'roles' else {p['id'] for p in current.get('permissions', [])}
    for values in data.values():
        if not isinstance(values, list) or len(values) > 500 or any(not isinstance(v, str) or len(v) > 256 for v in values) or len(set(values)) != len(values) or not set(values) <= allowed:
            raise ValueError('权限方案包含无效项目，请重新搜索')
    with closing(storage.connect()) as db, db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT profiles_json FROM jenkins_permission_profiles WHERE ip=?', (ip,)).fetchone()
        previous_revision = hashlib.sha256(previous['profiles_json'].encode('utf-8')).hexdigest() if previous else None
        if previous_revision != body.get('profileRevision'): raise ValueError('权限方案已变更，请重新搜索')
        stored = dict(data)
        # Preserve the retired profile for existing installations; it cannot be selected or applied.
        if previous:
            old_data = json.loads(previous['profiles_json'])
            if 'read' in old_data: stored['read'] = old_data['read']
        serialized = json.dumps(stored, ensure_ascii=False)
        db.execute('INSERT OR REPLACE INTO jenkins_permission_profiles (ip, strategy, profiles_json) VALUES (?, ?, ?)', (ip, strategy, serialized))
    return {'saved':True, 'revision':hashlib.sha256(serialized.encode('utf-8')).hexdigest()}


def save(body):
    username = _username(body); ip = body.get('ip'); revision = body.get('revision'); profile = body.get('profile')
    target = _targets().get(ip)
    if not target: raise ValueError('Jenkins 不存在，请重新搜索')
    if not isinstance(revision, str) or len(revision) != 64: raise ValueError('权限数据无效，请重新搜索')
    if 'selection' in body:
        strategy, values = body.get('strategy'), body.get('selection')
        if strategy not in ('matrix', 'roles') or not isinstance(values, list) or len(values) > 500 or any(not isinstance(v, str) or not v or len(v) > 256 for v in values) or len(set(values)) != len(values):
            raise ValueError('权限选择无效，请重新搜索')
        payload = {'action':'save_roles' if strategy == 'roles' else 'save', 'username':username, 'revision':revision}
        payload['roles' if strategy == 'roles' else 'permissions'] = values
        return _execute(target, payload)
    if profile not in ('qa', 'admin'): raise ValueError('权限方案无效，请重新搜索')
    with closing(storage.connect()) as db:
        row = db.execute('SELECT strategy, profiles_json FROM jenkins_permission_profiles WHERE ip=?', (ip,)).fetchone()
    if row is None: raise ValueError('请先配置并保存该 Jenkins 的权限方案')
    if hashlib.sha256(row['profiles_json'].encode('utf-8')).hexdigest() != body.get('profileRevision'): raise ValueError('权限方案已变更，请重新搜索')
    values = json.loads(row['profiles_json']).get(profile)
    if not values: raise ValueError('该权限方案为空，请先配置')
    payload = {'action':'save_roles' if row['strategy'] == 'roles' else 'save', 'username':username, 'revision':revision}
    payload['roles' if row['strategy'] == 'roles' else 'permissions'] = values
    return _execute(target, payload)
