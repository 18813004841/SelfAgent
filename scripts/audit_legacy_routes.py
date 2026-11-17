"""Report literal legacy API conditions and View registrations without executing services."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workbench/machine-dashboard-server/src"

def inventory():
    registered = {"GET": set(), "POST": set()}
    for path in (SOURCE / "view").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "route":
                values = [arg.value for arg in node.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
                if values and values[0] in registered:
                    registered[values[0]].update(values[1:])
    tree = ast.parse((SOURCE / "server.py").read_text(encoding="utf-8-sig"))
    result = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or fn.name not in ("_legacy_get", "_legacy_post"):
            continue
        method = fn.name.removeprefix("_legacy_").upper()
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "path" and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
                value = node.comparators[0]
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.startswith("/api/"):
                    covered = any(value.value.startswith(p[:-1]) if p.endswith("*") else value.value == p for p in registered[method])
                    result.append((method, value.value, "registered (inspect delegation)" if covered else "legacy only"))
    return sorted(set(result))

if __name__ == "__main__":
    print("| Method | Legacy condition | View registration |\n| --- | --- | --- |")
    for method, path, status in inventory():
        print(f"| {method} | `{path}` | {status} |")
    print("Scope: literal path equality only; registration does not prove implementation or exclude delegation.")
