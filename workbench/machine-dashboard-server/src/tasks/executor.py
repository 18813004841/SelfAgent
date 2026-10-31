import json, subprocess
from pathlib import Path
from core.storage import ROOT

def run_local_process(tool, args, timeout):
    entry = (ROOT / tool["entry"]).resolve()
    workdir = (ROOT / (tool["workdir"] or entry.parent)).resolve()
    if not entry.is_file() or not str(entry).startswith(str(ROOT)):
        raise RuntimeError("invalid tool entry")
    command = ["python", str(entry), "--input", json.dumps(args, ensure_ascii=False)]
    completed = subprocess.run(command, cwd=workdir, capture_output=True, text=True, timeout=timeout)
    result = {"returncode": completed.returncode, "stdout": completed.stdout[-10000:], "stderr": completed.stderr[-10000:]}
    if completed.returncode != 0: raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result

def run_tool(tool, args, timeout=300):
    if tool["type"] == "local_process": return run_local_process(tool, args, timeout)
    raise RuntimeError(f"unsupported tool type: {tool['type']}")

