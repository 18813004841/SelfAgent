"""Read the control center's current online worker addresses."""
import json
import os
import time
import urllib.request


def get_connections(port):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/workers",
        headers={"Authorization": f"Bearer {os.environ.get('MACHINE_CONTROL_TOKEN', 'dev-token')}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=0.8) as response:
            workers = json.loads(response.read().decode("utf-8"))["workers"]
        ips = []
        for worker in workers:
            if worker.get("status") != "online" or time.time() * 1000 - (worker.get("last_seen_at") or 0) >= 45000:
                continue
            for ip in worker.get("meta", {}).get("local_ips", []):
                if ip and ip not in ips and not ip.startswith("127."):
                    ips.append(ip)
        return {"ips": ips, "workers": workers, "available": True}
    except (OSError, ValueError, KeyError, TypeError):
        return {"ips": [], "workers": [], "available": False}
