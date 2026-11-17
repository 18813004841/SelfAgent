"""Run the client-owned acceptance verifier from the repository suite."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parents[1] / "workbench" / "machine-dashboard-client" / "scripts" / "validate_local_agent.py"),
        run_name="__main__",
    )
