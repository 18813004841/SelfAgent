"""Build a downloadable central-client package from the shared machine-control source."""
from pathlib import Path
import shutil
import tempfile
import argparse


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "packages"
PACKAGE = DIST / "central-client"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DIST)
    args = parser.parse_args()
    destination = args.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="machine-control-package-") as staging:
        package = Path(staging) / "central-client"
        package.mkdir()
        for source, target in ((ROOT / "client" / "control_worker", "control_worker"), (ROOT / "shared" / "common", "common"), (ROOT / "client" / "client_package", "client_package")):
            if not source.is_dir():
                raise FileNotFoundError(source)
            shutil.copytree(source, package / target, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "*.pyo", ".env", ".env.*", "*.local.json", "*.log", ".venv"))
        archive = shutil.make_archive(str(destination / "central-client"), "zip", staging, "central-client")
    print(archive)


if __name__ == "__main__":
    main()
