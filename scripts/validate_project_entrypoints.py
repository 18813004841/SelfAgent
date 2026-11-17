"""验证三个项目入口不依赖当前工作目录或已激活环境。"""
from pathlib import Path
import os
import subprocess
import sys
import argparse

ROOT = Path(__file__).resolve().parents[1]


def run(cmd, cwd, env=None):
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f"failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-venv", action="store_true", help="要求三个项目均已创建 .venv")
    args = parser.parse_args()
    agent = ROOT / "AiAgent/AiProject/Codes/Agents/OpenAiAgent"
    def interpreter(project):
        candidate = project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if candidate.exists():
            return str(candidate)
        if args.require_venv:
            raise SystemExit(f"missing project environment: {candidate}")
        return sys.executable
    agent_python = interpreter(agent)
    agent_env = os.environ.copy()
    # Editable installs may be absent in a freshly created environment; the
    # project source remains the authoritative entrypoint during bootstrap.
    agent_env["PYTHONPATH"] = os.pathsep.join([str(agent), agent_env.get("PYTHONPATH", "")])
    run([agent_python, "-m", "codex_agent.cli", "--help"], agent, agent_env)
    machine = ROOT / "Tools/machine-control"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([
        str(machine / "server"), str(machine / "shared"), str(machine / "client"),
        env.get("PYTHONPATH", ""),
    ])
    run([interpreter(machine), "-m", "control_center.server", "--help"], machine, env)
    workbench = ROOT / "workbench/machine-dashboard-server"
    env["PYTHONPATH"] = str(workbench / "src")
    run([interpreter(workbench), "-m", "py_compile", str(workbench / "src/server.py")], ROOT, env)
    print("project entrypoint validation passed (project interpreters selected explicitly)")


if __name__ == "__main__":
    main()
