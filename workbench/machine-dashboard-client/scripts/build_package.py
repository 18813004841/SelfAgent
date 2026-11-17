from __future__ import annotations
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

FILES = ["README.md", "AGENTS.md", "WORKBENCH_CLIENT_RULES.md", "pyproject.toml", "setup-client.ps1", "start-local-agent.bat", "stop-local-agent.ps1"]

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("dist/workbench-machine-dashboard-client.zip"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name in FILES:
            path = root / name
            if path.is_file(): archive.write(path, f"machine-dashboard-client/{name}")
        for path in (root / "src").glob("*.py"):
            archive.write(path, f"machine-dashboard-client/src/{path.name}")
    print(f"client package built: {output}")

if __name__ == "__main__": main()
