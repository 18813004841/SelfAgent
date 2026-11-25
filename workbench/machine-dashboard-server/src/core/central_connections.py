"""Read the control center's current online worker addresses."""
import json
import os
import time
import urllib.request


def get_connections(port, base_url=None):
    base_url = (base_url or os.environ.get("MACHINE_CONTROL_SERVER_URL") or f"http://127.0.0.1:{port}").rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/api/workers",
        headers={"Authorization": f"Bearer {os.environ.get('MACHINE_CONTROL_TOKEN', 'dev-token')}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=0.8) as response:
            workers = json.loads(response.read().decode("utf-8"))["workers"]
        ips = []
        now = time.time() * 1000
        for worker in workers:
            # The center persists the last registration status. Recompute it
            # from heartbeat time. Heartbeats are sent every 15 seconds; keep a
            # 45-second grace
            # period so a scheduling/network delay does not hide a live client,
            # while a stopped worker still expires promptly.
            fresh = now - (worker.get("last_seen_at") or 0) < 45000
            worker["status"] = "online" if fresh else "offline"
            if not fresh:
                continue
            for ip in worker.get("meta", {}).get("local_ips", []):
                if ip and ip not in ips and not ip.startswith("127."):
                    ips.append(ip)
        return {"ips": ips, "workers": workers, "available": True}
    except (OSError, ValueError, KeyError, TypeError):
        return {"ips": [], "workers": [], "available": False}
