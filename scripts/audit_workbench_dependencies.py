"""报告工作台源码使用但依赖清单未声明的第三方顶层模块。"""
from __future__ import annotations
import ast, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "workbench/machine-dashboard-server"
STDLIB = {"abc","argparse","asyncio","base64","collections","concurrent","configparser","contextlib","contextvars","ctypes","dataclasses","datetime","enum","fnmatch","functools","glob","hashlib","http","importlib","inspect","io","json","logging","math","mimetypes","os","pathlib","platform","random","re","secrets","shlex","shutil","signal","socket","sqlite3","statistics","string","subprocess","sys","tempfile","threading","time","traceback","typing","unittest","urllib","uuid","xml","zipfile","zoneinfo"}

def imports() -> set[str]:
    result = set()
    for path in list((PROJECT / "src").rglob("*.py")) + list((PROJECT / "launchers").rglob("*.py")):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            raise SystemExit(f"cannot parse workbench source: {path}: {exc}") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                candidates = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                candidates = [node.module.split(".")[0]]
            else:
                continue
            for name in candidates:
                # Script-local absolute imports are resolvable only beside this
                # source file, not beside an unrelated module elsewhere.
                if (path.parent / f"{name}.py").is_file() or (path.parent / name).is_dir():
                    continue
                result.add(name)
    return result

def declared() -> set[str]:
    result = set()
    for file in (PROJECT / "requirements.txt", PROJECT / "requirements-dev.txt"):
        if file.exists():
            raw = file.read_bytes()
            text = raw.decode("utf-16") if raw.startswith(b"\xff\xfe") else raw.decode("utf-8-sig")
            for line in text.splitlines():
                match = re.match(r"\s*([A-Za-z0-9_.-]+)", line)
                if match and not line.lstrip().startswith("#"): result.add(match.group(1).lower().replace("-", "_"))
    return result

def main() -> None:
    local = {p.name for p in (PROJECT / "src").iterdir() if p.is_dir()} | {p.name for p in (PROJECT / "launchers").iterdir() if p.is_dir()}
    local |= {p.stem for p in (PROJECT / "src").glob("*.py")}
    local |= {"launchers"}
    modules = imports() - STDLIB - local - {"__future__", "tkinter"}
    names = {name.lower().replace("-", "_") for name in declared()}
    # Known distribution/module spelling differences.
    aliases = {"dotenv": "python_dotenv", "PIL": "pillow"}
    missing = sorted(m for m in modules if aliases.get(m, m).lower().replace("-", "_") not in names)
    if missing:
        raise SystemExit("undeclared workbench imports: " + ", ".join(missing))
    print("workbench dependency audit passed")

if __name__ == "__main__": main()
