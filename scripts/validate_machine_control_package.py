"""Validate the generated machine-control client archive contents."""
from pathlib import Path
from zipfile import ZipFile
import subprocess
import sys
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]

def validate(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        assert archive.testzip() is None
        assert "central-client/control_worker/executor.py" in names
        for source, folder in ((ROOT / "Tools/machine-control/client/control_worker", "control_worker"),
                               (ROOT / "Tools/machine-control/shared/common", "common")):
            for module in source.glob("*.py"):
                assert archive.read(f"central-client/{folder}/{module.name}") == module.read_bytes(), module
        forbidden = ("__pycache__", ".pyc", ".pyo", ".log", ".local.json", ".env")
        assert not any(any(item in name for item in forbidden) for name in names), names

def validate_runtime(path):
    with tempfile.TemporaryDirectory(prefix="machine-control-client-runtime-") as extracted:
        with ZipFile(path) as archive:
            archive.extractall(extracted)
        root = Path(extracted) / "central-client"
        env = {**os.environ, "PYTHONPATH": "", "PYTHONNOUSERSITE": "1"}
        subprocess.run([sys.executable, "-S", "-m", "control_worker.client", "--help"],
                       cwd=root, env=env, check=True, timeout=15, stdout=subprocess.DEVNULL)

def main() -> None:
    with tempfile.TemporaryDirectory(prefix="machine-control-package-check-") as temporary:
        subprocess.run([sys.executable, str(ROOT / "Tools/machine-control/scripts/build_client_package.py"),
                        "--output-dir", temporary], check=True, capture_output=True)
        archive = Path(temporary) / "central-client.zip"
        validate(archive)
        validate_runtime(archive)
    print("machine-control client package validation passed")

if __name__ == "__main__":
    main()
