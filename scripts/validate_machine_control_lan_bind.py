"""Validate LAN bind and authenticated access from the host's non-loopback IPv4."""
import json, os, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "Tools/machine-control"

def local_ip():
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    finally:
        probe.close()

def get(url, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read())

def main():
    ip = local_ip()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="selfagent-lan-bind-") as td:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(MACHINE / "server"), str(MACHINE / "shared")])
        proc = subprocess.Popen([sys.executable, "-m", "control_center.server", "--host", "0.0.0.0", "--port", str(port), "--token", "lan-bind-token", "--store", str(Path(td) / "center.json")], cwd=MACHINE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://{ip}:{port}"
            for _ in range(40):
                try:
                    status, body = get(base + "/health")
                    if status == 200 and body.get("ok"):
                        break
                except Exception:
                    time.sleep(.1)
            else:
                raise AssertionError("LAN address did not reach bound center")
            try:
                get(base + "/api/workers")
            except urllib.error.HTTPError as error:
                assert error.code == 401
            else:
                raise AssertionError("protected endpoint accepted missing token")
            status, body = get(base + "/api/workers", "lan-bind-token")
            assert status == 200 and body.get("ok") is True
            print("machine-control LAN bind/auth validation passed")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=5)
            assert proc.poll() is not None

if __name__ == "__main__":
    main()
