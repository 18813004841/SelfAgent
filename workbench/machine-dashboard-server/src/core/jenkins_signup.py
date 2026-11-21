"""Register users using Jenkins' self-signup form; passwords are never persisted."""
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from html.parser import HTMLParser
from core import storage
from core.jenkins import NoRedirect, url_for


class SignupForm(HTMLParser):
    def __init__(self):
        super().__init__(); self.inside = False; self.action = None; self.hidden = {}; self.captcha = False
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form' and 'securityRealm/createAccount' in a.get('action', ''):
            self.inside = True; self.action = a.get('action')
        if self.inside and tag == 'input':
            name = a.get('name', '')
            if name == 'captcha': self.captcha = True
            if a.get('type', '').lower() == 'hidden' and name: self.hidden[name] = a.get('value', '')
    def handle_endtag(self, tag):
        if tag == 'form': self.inside = False


def _one(item, values):
    base = url_for(item['ip'], item['scheme'], item['port'])
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect, urllib.request.ProxyHandler({}))
    try:
        with opener.open(base + 'signup', timeout=5) as response:
            page = response.read(1024 * 1024).decode('utf-8', 'replace')
        form = SignupForm(); form.feed(page)
        if not form.action: return '该实例未提供支持的自助注册表单'
        if form.captcha: return '该实例要求验证码，请在 Jenkins 页面注册'
        target = urllib.parse.urljoin(base, form.action)
        if urllib.parse.urlsplit(target)[:2] != urllib.parse.urlsplit(base)[:2] or urllib.parse.urlsplit(target).path != '/securityRealm/createAccount':
            return '注册表单地址不受支持'
        fields = {**form.hidden, **values, 'password2': values['password1']}
        request = urllib.request.Request(target, data=urllib.parse.urlencode(fields).encode(), method='POST')
        with opener.open(request, timeout=8) as response:
            response.read(1024 * 1024)
        with opener.open(base + 'whoAmI/api/json', timeout=5) as response:
            identity = json.loads(response.read(65536))
        if identity.get('authenticated') is True and identity.get('name') == values['username']:
            return '注册成功'
        return '结果未能确认，请在 Jenkins 检查账号'
    except urllib.error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308): return '结果未能确认，请在 Jenkins 检查账号'
        if exc.code in (401, 403): return '注册被拒绝，请检查自助注册配置'
        return f'Jenkins 返回 HTTP {exc.code}'
    except (urllib.error.URLError, TimeoutError, OSError):
        return '连接失败或超时，若请求已提交请先检查账号'
    except (ValueError, KeyError):
        return '结果未能确认，请在 Jenkins 检查账号'


def register_accounts(body):
    ips = body.get('ips'); username = body.get('username'); fullname = body.get('fullname'); email = body.get('email', ''); password = body.get('password')
    if not isinstance(ips, list) or not ips or len(ips) > 50 or any(not isinstance(ip, str) for ip in ips): raise ValueError('请选择有效的 Jenkins')
    if not all(isinstance(v, str) for v in (username, fullname, email, password)) or not username.strip() or not fullname.strip() or not password: raise ValueError('请填写用户名、全称和密码')
    if len(username) > 128 or len(fullname) > 256 or len(email) > 320 or len(password) > 1024: raise ValueError('输入内容过长')
    ips = list(dict.fromkeys(ips))
    with closing(storage.connect()) as db:
        rows = {r['ip']: dict(r) for r in db.execute('SELECT ip, scheme, port FROM jenkins_servers')}
    if any(ip not in rows for ip in ips): raise ValueError('所选 Jenkins 不存在，请刷新列表')
    values = {'username': username.strip(), 'fullname': fullname.strip(), 'email': email.strip(), 'password1': password}
    return [{'ip': ip, 'message': _one(rows[ip], values)} for ip in ips]
