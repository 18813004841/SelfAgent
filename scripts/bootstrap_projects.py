"""初始化 SelfAgent 三个项目的独立虚拟环境。

默认创建缺失环境并安装依赖；--no-install 只创建环境。
已有环境不重建，但默认安装可能改变其中的软件包。网络和安装权限由调用环境决定。
"""
from pathlib import Path
import argparse
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = {
    "workbench": (ROOT / "workbench/machine-dashboard-server", "requirements.txt"),
    "machine-control": (ROOT / "Tools/machine-control", "pyproject.toml"),
    "aiagent": (ROOT / "AiAgent/AiProject/Codes/Agents/OpenAiAgent", "pyproject.toml"),
}


def python_path(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command, cwd):
    print("+", " ".join(map(str, command)))
    subprocess.run(command, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=[*PROJECTS, "all"], default="all")
    parser.add_argument("--upgrade", action="store_true", help="升级 pip 并重装项目")
    parser.add_argument("--no-install", action="store_true", help="只创建缺失环境，不安装或修改已有环境")
    parser.add_argument("--verify", action="store_true", help="安装后使用项目解释器验证入口")
    parser.add_argument("--frozen", action="store_true", help="要求项目存在锁文件并使用锁定安装")
    args = parser.parse_args()
    if args.no_install and args.upgrade:
        parser.error("--no-install 不能与 --upgrade 一起使用")
    if args.frozen and (args.no_install or args.upgrade):
        parser.error("--frozen 不能与 --no-install 或 --upgrade 一起使用")
    names = PROJECTS if args.project == "all" else {args.project: PROJECTS[args.project]}
    # Validate the entire selection before creating or changing any environment.
    if args.frozen:
        for name, (project, manifest) in names.items():
            if manifest != "pyproject.toml":
                parser.error(f"{name} 暂不支持 --frozen；运行清单尚无完整传递依赖锁")
            if not (project / "uv.lock").is_file():
                parser.error(f"--frozen requires lock file: {project / 'uv.lock'}")
    for name, (project, manifest) in names.items():
        venv = project / ".venv"
        if not venv.exists():
            run([sys.executable, "-m", "venv", str(venv)], ROOT)
        interpreter = python_path(venv)
        if args.upgrade:
            run([str(interpreter), "-m", "pip", "install", "--upgrade", "pip"], project)
        if args.no_install:
            print(f"environment ready: {name} -> {interpreter}")
            continue
        if manifest.endswith("requirements.txt"):
            requirement_file = project / manifest
            run([str(interpreter), "-m", "pip", "install", "-r", str(requirement_file)], project)
        else:
            lock = project / "uv.lock"
            if args.frozen:
                if not lock.exists():
                    raise SystemExit(f"--frozen requires lock file: {lock}")
                run(["uv", "sync", "--locked"], project)
            else:
                run([str(interpreter), "-m", "pip", "install", "-e", "."], project)
        print(f"ready: {name} -> {interpreter}")
    if args.verify:
        verify = ROOT / "scripts" / "validate_project_entrypoints.py"
        run([sys.executable, str(verify), "--require-venv"], ROOT)


if __name__ == "__main__":
    main()
