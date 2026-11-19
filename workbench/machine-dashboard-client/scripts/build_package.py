from __future__ import annotations
import argparse
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

FILES = ["README.md", "AGENTS.md", "WORKBENCH_CLIENT_RULES.md", "pyproject.toml", "VERSION", "setup-client.ps1", "update-client.ps1", "start-local-agent.bat", "start-local-agent.sh", "start-local-agent.command", "stop-local-agent.ps1"]
SCRIPTS = ["start_local_codex.bat"]

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("dist/workbench-machine-dashboard-client.zip"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not version:
        raise SystemExit("VERSION is empty")
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', project, re.MULTILINE)
    if not match or match.group(1) != version:
        raise SystemExit("VERSION and pyproject.toml version do not match")
    output = args.output.resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name in FILES:
            path = root / name
            if path.is_file(): archive.write(path, f"machine-dashboard-client/{name}")
        for path in (root / "src").glob("*.py"):
            archive.write(path, f"machine-dashboard-client/src/{path.name}")
        for name in SCRIPTS:
            path = root / "scripts" / name
            if not path.is_file():
                raise SystemExit(f"required client script missing: {name}")
            archive.write(path, f"machine-dashboard-client/scripts/{name}")
    print(f"client package built: {output}")

if __name__ == "__main__": main()
