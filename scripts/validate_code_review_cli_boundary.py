"""验证工作台代码检查适配器的子进程 JSON 边界。"""
import json
import sys
import tempfile
from pathlib import Path


def main():
    with tempfile.TemporaryDirectory(prefix="selfagent-cli-boundary-") as root:
        tool_root = Path(root)
        (tool_root / "run_task.py").write_text(
            "import argparse,json\n"
            "p=argparse.ArgumentParser(); p.add_argument('--input'); a=p.parse_args()\n"
            "print(json.dumps({'status':'succeeded','echo':json.loads(a.input)}))\n",
            encoding="utf-8",
        )
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workbench/machine-dashboard-server/src"))
        from integrations.code_review_cli import CodeReviewCli
        payload = {"project_path": str(tool_root), "branch": "main"}
        result = CodeReviewCli(tool_root).run(payload)
        assert result["status"] == "succeeded"
        assert result["echo"] == payload
        print("code review CLI boundary validation passed")


if __name__ == "__main__":
    main()

