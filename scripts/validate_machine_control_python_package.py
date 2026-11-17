"""Validate the isolated machine-control Python distribution build."""
from pathlib import Path
import subprocess
import sys
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "Tools" / "machine-control"


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="selfagent-python-dist-") as raw:
        output = Path(raw)
        subprocess.run(
            [sys.executable, "scripts/build_python_package.py", "--output-dir", str(output)],
            cwd=PROJECT, check=True, timeout=180,
        )
        names = {path.suffix for path in output.iterdir()}
        assert ".whl" in names and ".gz" in names, sorted(names)
        wheel = next(output.glob("*.whl"))
        env_dir = output / "env"
        subprocess.run(["uv", "venv", str(env_dir)], check=True, capture_output=True, timeout=60)
        python = env_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(["uv", "pip", "install", "--python", str(python), str(wheel)], check=True, timeout=120)
        clean_env = os.environ.copy()
        clean_env.pop("PYTHONPATH", None)
        clean_env["PYTHONNOUSERSITE"] = "1"
        for module in ("control_center.server", "control_worker.client"):
            subprocess.run(
                [str(python), "-I", "-m", module, "--help"],
                check=True, env=clean_env, cwd=output, timeout=30,
            )
    assert not (PROJECT / "selfagent_machine_control.egg-info").exists()
    print("machine-control isolated Python package validation passed")


if __name__ == "__main__":
    main()
