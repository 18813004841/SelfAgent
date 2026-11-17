from __future__ import annotations
import subprocess
import sys
import tempfile
import socket
import time
import json
import urllib.request
from pathlib import Path
from zipfile import ZipFile

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    builder = root / "workbench/machine-dashboard-client/scripts/build_package.py"
    with tempfile.TemporaryDirectory(prefix="wb-client-package-") as temp:
        output = Path(temp) / "client.zip"
        result = subprocess.run([sys.executable, str(builder), "--output", str(output)], cwd=root, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        with ZipFile(output) as archive:
            names = archive.namelist()
            assert "machine-dashboard-client/src/local_agent.py" in names
            assert "machine-dashboard-client/setup-client.ps1" in names
            assert not any(".venv" in name or name.endswith((".sqlite", ".log", "settings.json")) for name in names)
            archive.extractall(Path(temp) / "extracted")
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        profile = Path(temp) / "profile"
        process = subprocess.Popen([sys.executable, "-m", "src.local_agent", "--port", str(port), "--data-dir", str(profile), "--dashboard-url", "http://192.168.1.10:18888"], cwd=Path(temp) / "extracted/machine-dashboard-client", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(50):
                if process.poll() is not None:
                    raise AssertionError("extracted client exited before readiness")
                try:
                    call = urllib.request.Request(f"http://127.0.0.1:{port}/api/settings/storage", headers={"Origin": "http://192.168.1.10:18888"})
                    with urllib.request.urlopen(call, timeout=1) as response:
                        settings = json.load(response)["settings"]
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise AssertionError("extracted client readiness timeout")
            assert Path(settings["storage_dir"]).resolve() == (profile / "client/storage").resolve()
            assert Path(settings["config_path"]).resolve() == (profile / "config/settings.json").resolve()
        finally:
            process.terminate()
            process.wait(timeout=5)
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", port)) != 0
    print("client distribution validation passed")

if __name__ == "__main__":
    main()
