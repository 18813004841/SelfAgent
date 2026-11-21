"""Read and update Jenkins global matrix authorization via its administrator script endpoint."""
import base64
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
    try { j.securityRealm.loadUserByUsername2(input.username); exists = true }
    catch (org.springframework.security.core.userdetails.UsernameNotFoundException ignored) { exists = false }
    catch (Exception ignored) { exists = null }
    def grants = a.grantedPermissionEntries
    def fingerprint = { m ->
      def lines = []
      m.each { p, entries -> entries.each { e -> lines << (p.id + '\t' + e.type.name() + '\t' + e.sid) } }
      MessageDigest.getInstance('SHA-256').digest(lines.sort().join('\n').getBytes('UTF-8')).encodeHex().toString()
    }
    def permissions = PermissionGroup.all.collectMany { g -> g.permissions.findAll { it.enabled }.collect { p -> [id:p.id, group:g.title.toString(), name:p.name] } }.sort { it.id }
    def current = [] as Set
    def ambiguous = false
    grants.each { p, entries -> entries.each { e ->
      if (j.securityRealm.userIdStrategy.equals(e.sid, input.username) && e.type == AuthorizationType.USER) current.add(p.id)
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
          if (!(e.type == AuthorizationType.USER && j.securityRealm.userIdStrategy.equals(e.sid, input.username))) next.add(p, e)
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
        script = _SCRIPT.replace('__PAYLOAD__', encoded)
        data = urllib.parse.urlencode({'script': script}).encode()
        with opener.open(urllib.request.Request(base + 'scriptText', data=data, headers=headers), timeout=15) as response:
            content = response.read(2 * 1024 * 1024).decode('utf-8', 'replace')
        lines = [line[len('WORKBENCH_JSON:'):] for line in content.splitlines() if line.startswith('WORKBENCH_JSON:')]
        if len(lines) != 1: raise RuntimeError('Jenkins 返回了无法识别的结果')
        result = json.loads(lines[0])
        if result.get('error'): raise RuntimeError(result['error'])
        return result
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


def search(body):
    username = _username(body)
    targets = _targets()
    def read(pair):
        ip, item = pair
        try: return {'ip': ip, **_execute(item, {'action':'search', 'username':username})}
        except (RuntimeError, ValueError) as exc: return {'ip': ip, 'error': str(exc)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(read, targets.items()))


def save(body):
    username = _username(body); ip = body.get('ip'); revision = body.get('revision'); permissions = body.get('permissions')
    targets = _targets()
    if not isinstance(ip, str) or ip not in targets: raise ValueError('Jenkins 不存在，请重新搜索')
    if not isinstance(revision, str) or len(revision) != 64 or not isinstance(permissions, list) or len(permissions) > 500 or any(not isinstance(p, str) or len(p) > 256 for p in permissions): raise ValueError('权限数据无效，请重新搜索')
    return _execute(targets[ip], {'action':'save', 'username':username, 'revision':revision, 'permissions':permissions})
