"""Jenkins configuration and bounded service status detection."""
import ipaddress
import sqlite3
import urllib.error
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
                cursor = db.execute('UPDATE jenkins_servers SET ip=?, scheme=?, port=? WHERE ip=?', (ip, scheme, port, old_ip))
                if cursor.rowcount == 0:
                    raise ValueError('Jenkins 条目不存在')
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
