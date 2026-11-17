"""Run the distributable Windows client setup script in an isolated profile."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path


def run(script: Path, profile: Path, url: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "LOCALAPPDATA": str(profile)}
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-DashboardUrl", url],
        cwd=script.parent,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "workbench" / "machine-dashboard-client" / "setup-client.ps1"
    with tempfile.TemporaryDirectory(prefix="wb-client-setup-") as temporary:
        profile = Path(temporary) / "LocalAppData"
        first = run(script, profile, "http://192.168.1.10:18888")
        assert first.returncode == 0, first.stderr
        config = profile / "LocalWorkbench" / "config" / "settings.json"
        default = profile / "LocalWorkbench" / "client" / "storage"
        value = json.loads(config.read_text(encoding="utf-8"))
        assert value["storage_dir"] == str(default), value
        assert value["dashboard_url"] == "http://192.168.1.10:18888", value

        second_profile = Path(temporary) / "SecondClient" / "LocalAppData"
        second = run(script, second_profile, "http://192.168.1.10:18888")
        assert second.returncode == 0, second.stderr
        second_config = second_profile / "LocalWorkbench" / "config" / "settings.json"
        second_value = json.loads(second_config.read_text(encoding="utf-8"))
        assert second_value["storage_dir"] != value["storage_dir"]
        assert second_value["storage_dir"].endswith("LocalWorkbench\\client\\storage")

        custom = profile / "custom-storage"
        config.write_text(json.dumps({"storage_dir": str(custom), "dashboard_url": "http://old:18888"}), encoding="utf-8")
        second = run(script, profile, "http://192.168.1.10:18888")
        assert second.returncode == 0, second.stderr
        value = json.loads(config.read_text(encoding="utf-8"))
        assert value["storage_dir"] == str(custom), value
        assert value["dashboard_url"] == "http://192.168.1.10:18888", value

        invalid = run(script, profile / "invalid", "http://192.168.1.10:18888/path")
        assert invalid.returncode != 0, invalid.stdout
    print("client setup validation passed")


if __name__ == "__main__":
    main()
