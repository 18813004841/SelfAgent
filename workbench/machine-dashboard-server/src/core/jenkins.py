"""Jenkins configuration and bounded service status detection."""
import ipaddress
import json
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from core import storage
from core.central_connections import get_connections


def normalize(body):
    try:
        ip = str(ipaddress.ip_address(str(body.get("ip", "")).strip()))
    except ValueError:
        raise ValueError("请输入有效的 IP 地址") from None
    scheme = body.get("scheme")
    if scheme not in ("http", "https"):
        raise ValueError("协议必须为 HTTP 或 HTTPS")
    port = body.get("port")
    if isinstance(port, bool) or not str(port).isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("端口必须为 1 到 65535 的整数")
    return ip, scheme, int(port)


def url_for(ip, scheme, port):
    host = f"[{ip}]" if ':' in ip else ip
    return f"{scheme}://{host}:{port}/"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def last_completed(body):
    """Read one registered Jenkins job anonymously; never forward credentials."""
    ip = body.get('ip')
    job = body.get('job')
    if not isinstance(ip, str) or not isinstance(job, str):
        raise ValueError('请输入 Jenkins IP 和任务路径')
    try:
        ip = str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        raise ValueError('请输入有效的 Jenkins IP') from None
    parts = job.strip().split('/')
    if len(parts) > 20 or any(not p or p in ('.', '..') or len(p) > 200 or any(ord(c) < 32 or c in '\\%' for c in p) for p in parts):
        raise ValueError('请输入有效的任务路径，文件夹以 / 分隔')
    with closing(storage.connect()) as db:
        row = db.execute('SELECT ip, scheme, port FROM jenkins_servers WHERE ip=?', (ip,)).fetchone()
    if not row:
        raise ValueError('该 Jenkins 未登记')
    item = dict(row)
    path = ''.join('job/' + urllib.parse.quote(p, safe='') + '/' for p in parts)
    url = url_for(item['ip'], item['scheme'], item['port']) + path + 'lastCompletedBuild/api/json?tree=number,result'
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, method='GET'), timeout=5) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            raise RuntimeError('Jenkins 响应过大')
        data = json.loads(raw)
        number, result = data['number'], data['result']
        if isinstance(number, bool) or not isinstance(number, int) or number < 0 or result not in ('SUCCESS', 'FAILURE', 'UNSTABLE', 'ABORTED', 'NOT_BUILT'):
            raise ValueError('invalid response')
        return {'number': number, 'result': result}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError('Jenkins 拒绝匿名读取，请使用 Jenkins 原页面登录查看') from None
        if exc.code == 404:
            raise RuntimeError('任务或已完成构建不存在，或 Jenkins 未授权访问') from None
        raise RuntimeError(f'Jenkins 返回 HTTP {exc.code}') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError('连接 Jenkins 失败或超时') from None
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('Jenkins 返回的数据格式无效') from None


def probe(item):
    request = urllib.request.Request(url_for(item['ip'], item['scheme'], item['port']), method="GET")
    try:
        try:
            response = urllib.request.build_opener(NoRedirect).open(request, timeout=2)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return "online" if response.headers.get("X-Jenkins") is not None else "offline"
    except (urllib.error.URLError, TimeoutError, OSError):
        return "offline"
    except Exception:
        return "unknown"


def list_servers(center_port):
    with closing(storage.connect()) as db, db:
        items = [dict(row) for row in db.execute('SELECT ip, scheme, port FROM jenkins_servers ORDER BY ip')]
    connections = get_connections(center_port)
    connected = set()
    for ip in connections['ips']:
        try:
            connected.add(str(ipaddress.ip_address(ip)))
        except ValueError:
            continue
    with ThreadPoolExecutor(max_workers=8) as executor:
        statuses = list(executor.map(probe, items))
    for item, status in zip(items, statuses):
        item['url'] = url_for(item['ip'], item['scheme'], item['port'])
        item['online'] = status
        item['connected'] = ('connected' if item['ip'] in connected else 'disconnected') if connections['available'] else 'unknown'
    return items


def save(body):
    ip, scheme, port = normalize(body)
    old_ip = body.get('old_ip')
    try:
        with closing(storage.connect()) as db, db:
            if old_ip is None:
                db.execute('INSERT INTO jenkins_servers (ip, scheme, port) VALUES (?, ?, ?)', (ip, scheme, port))
            else:
                try:
                    old_ip = str(ipaddress.ip_address(str(old_ip).strip()))
                except ValueError:
                    raise ValueError('原 IP 地址无效') from None
                previous = db.execute('SELECT ip, scheme, port FROM jenkins_servers WHERE ip=?', (old_ip,)).fetchone()
                cursor = db.execute('UPDATE jenkins_servers SET ip=?, scheme=?, port=? WHERE ip=?', (ip, scheme, port, old_ip))
                if cursor.rowcount == 0:
                    raise ValueError('Jenkins 条目不存在')
                if previous and (old_ip != ip or previous['scheme'] != scheme or previous['port'] != port):
                    db.execute('DELETE FROM jenkins_permission_profiles WHERE ip=?', (old_ip,))
    except sqlite3.IntegrityError:
        raise ValueError('该 IP 已存在') from None


def delete(body):
    try:
        ip = str(ipaddress.ip_address(str(body.get('ip', '')).strip()))
    except ValueError:
        raise ValueError('请输入有效的 IP 地址') from None
    with closing(storage.connect()) as db, db:
        if db.execute('DELETE FROM jenkins_servers WHERE ip=?', (ip,)).rowcount == 0:
            raise ValueError('Jenkins 条目不存在')
        db.execute('DELETE FROM jenkins_permission_profiles WHERE ip=?', (ip,))
