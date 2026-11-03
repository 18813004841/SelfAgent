"""Build a downloadable central-client package from the shared machine-control source."""
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "packages"
PACKAGE = DIST / "central-client"


def main() -> None:
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    PACKAGE.mkdir(parents=True)
    for source, target in ((ROOT / "client" / "control_worker", "control_worker"), (ROOT / "shared" / "common", "common"), (ROOT / "client" / "client_package", "client_package")):
        if source.exists():
            shutil.copytree(source, PACKAGE / target)
    archive = shutil.make_archive(str(DIST / "central-client"), "zip", DIST, "central-client")
    print(archive)


if __name__ == "__main__":
    main()
