"""Run the local architecture regression suite; external acceptance is separate."""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKS = [
    ("check_architecture.py", "--tracked-artifacts", "--tracked-local-config"),
    ("validate_document_links.py",),
    ("validate_architecture_boundary.py",),
    ("audit_workbench_dependencies.py",),
    ("validate_bootstrap_contract.py",),
    ("validate_project_entrypoints.py", "--require-venv"),
    ("validate_workbench_storage.py",),
    ("validate_repositories.py",),
    ("validate_storage_concurrency.py",),
    ("validate_workbench_settings.py",),
    ("validate_workbench_logging.py",),
    ("validate_workbench_http.py",),
    ("validate_workbench_lan_bind.py",),
    ("validate_workbench_web.py",),
    ("validate_workbench_local_agent.py",),
    ("validate_client_setup.py",),
    ("validate_client_distribution.py",),
    ("validate_page_scope.mjs",),
    ("validate_review_data_migration.py",),
    ("validate_process_manager.py",),
    ("validate_port_conflict.py",),
    ("validate_launcher_ownership.py",),
    ("validate_machine_control_cancel.py",),
    ("validate_worker_process_cancel.py",),
    ("validate_machine_control_running_cancel.py",),
    ("validate_machine_control_lan_bind.py",),
    ("validate_machine_control_package.py",),
    ("validate_machine_control_python_package.py",),
    ("validate_joint_runtime.py",),
]


def main():
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js is required for page lifecycle validation")
    for filename, *args in CHECKS:
        interpreter = node if filename.endswith(".mjs") else sys.executable
        command = [interpreter, str(ROOT / "scripts" / filename), *args]
        print(f"Running {filename}", flush=True)
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode:
            raise SystemExit(result.returncode)
    print(f"Local regression passed: {len(CHECKS)} checks; external acceptance remains separate")


if __name__ == "__main__":
    main()
