"""Verify the workbench binds on all interfaces and answers on a LAN address."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def local_ipv4() -> str | None:
    addresses = {item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    return next((value for value in addresses if not value.startswith(("127.", "169.254."))), None)


def main() -> None:
    address = local_ipv4()
    if not address:
        print("workbench LAN bind skipped: no non-loopback IPv4 on this host")
        return
    root = Path(__file__).resolve().parents[1]
    server = root / "workbench" / "machine-dashboard-server" / "src" / "server.py"
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    env = {**os.environ, "LOCALAPPDATA": tempfile.mkdtemp(prefix="wb-lan-"), "MACHINE_DASHBOARD_PORT": str(port), "PYTHONPATH": str(server.parent)}
    env.pop("MACHINE_DASHBOARD_HOST", None)
    process = subprocess.Popen([sys.executable, str(server)], cwd=server.parent.parent, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        url = f"http://{address}:{port}/api/health"
        for _ in range(60):
            if process.poll() is not None:
                raise AssertionError(f"workbench exited: {process.returncode}")
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    body = json.loads(response.read())
                assert body["ok"] and body["service"] == "machine-dashboard-server", body
                print(f"workbench LAN bind validation passed: {address}:{port}")
                return
            except Exception:
                time.sleep(0.1)
        raise AssertionError(f"LAN health timeout: {url}")
    finally:
        process.terminate()
        process.wait(timeout=5)


if __name__ == "__main__":
    main()
