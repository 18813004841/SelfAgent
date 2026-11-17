"""Build the Python distribution from an isolated staging tree."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY_PATHS = ["pyproject.toml", "README.md", "server", "client", "shared"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="machine-control-build-") as raw:
        staging = Path(raw) / "project"
        staging.mkdir()
        for name in COPY_PATHS:
            source = ROOT / name
            target = staging / name
            if source.is_dir():
                for module in source.rglob("*.py"):
                    if "__pycache__" in module.parts or module.is_symlink():
                        continue
                    destination = target / module.relative_to(source)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(module, destination)
            else:
                shutil.copy2(source, target)
        subprocess.run(["uv", "build", "--out-dir", str(args.output_dir)], cwd=staging, check=True)
    print(f"isolated Python package build passed: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
