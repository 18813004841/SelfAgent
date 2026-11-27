"""Exercise Codex batch coverage and persisted execution records in a disposable Git repo."""
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench/machine-dashboard-server/tools/code-review-agent"))
sys.path.insert(0, str(ROOT / "workbench/machine-dashboard-server/src"))


def main():
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        os.environ["WORKBENCH_CODE_REVIEW_DATA_DIR"] = str(work / "data")
        os.environ["WORKBENCH_CODE_REVIEW_LOG_DIR"] = str(work / "logs")
        from code_review.config import ReviewConfig
        from code_review.codex_runner import CodexRunnerError
        from code_review.pipeline import ReviewPipeline

        repo = work / "project"
        repo.mkdir()
        def git(*args):
            return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()
        git("init", "-b", "main")
        git("config", "user.name", "Test Author")
        git("config", "user.email", "test@example.com")
        (repo / "initial.txt").write_text("base", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "base")
        old = git("rev-parse", "HEAD")
        for name in ("A", "B", "C"):
            path = repo / "Game" / "Assets" / "Feature" / f"{name}.cs"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"class {name} {{}}\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "change")
        config = ReviewConfig({"project": {"path": str(repo), "branch": "main", "clean_before_sync": False}, "model_service": {"backend": "codex", "model": "test-model", "codex_batch_files": 2}, "checks": {}})
        calls = []
        fail_last = True
        def run(_self, prompt, cancel):
            files = json.loads(re.search(r"本批必须逐个审查的变更文件：(\[.*\])", prompt).group(1))
            calls.append(files)
            reviewed = files[:-1] if fail_last and len(files) == 1 else files
            return json.dumps({"reviewed_files": reviewed, "findings": [{"severity": "medium", "message": "test", "file": name, "line": 1} for name in files]})
        with patch("code_review.pipeline.CodexRunner.run", run), patch("code_review.pipeline.notify", return_value=[]):
            first = ReviewPipeline(config)
            with patch.object(first, "load_previous_sha", return_value=old):
                failed = first.run()
            assert failed.status == "error" and len(calls) == 2
            assert len(failed.findings) == 2 and len(failed.as_display_dict()["失败切片"]) == 1
            report1 = Path(failed.report_path)
            manifest = json.loads((report1.parent / "review-manifest.json").read_text(encoding="utf-8"))
            assert manifest["model"] == "test-model" and [x["status"] for x in manifest["batches"]] == ["passed", "failed"]
            assert (report1.parent / "codex-input-001.md").is_file() and (report1.parent / "codex-output-002.txt").is_file()
            assert not (report1.parents[2] / "state.json").exists()
            fail_last = False
            calls.clear()
            second = ReviewPipeline(config)
            with patch.object(second, "load_previous_sha", return_value=old):
                completed = second.run()
            assert completed.status == "passed" and len(completed.findings) == 3 and len(calls) == 2
            assert Path(completed.report_path) != report1 and report1.is_file()
            assert json.loads((report1.parents[2] / "state.json").read_text(encoding="utf-8"))["last_successful_sha"] == git("rev-parse", "HEAD")
        with patch("code_review.pipeline.CodexRunner.run", side_effect=CodexRunnerError("model_not_in_accessible_catalog model_not_found")) as run_model, patch("code_review.pipeline.notify", return_value=[]):
            third = ReviewPipeline(config)
            with patch.object(third, "load_previous_sha", return_value=old):
                unavailable = third.run()
            assert unavailable.status == "error" and run_model.call_count == 1
            manifest = json.loads((Path(unavailable.report_path).parent / "review-manifest.json").read_text(encoding="utf-8"))
            assert [batch["status"] for batch in manifest["batches"]] == ["failed", "not_started"]
            assert len(unavailable.as_display_dict()["失败切片"]) == 2
        logging.shutdown()
        print("PASS: batch coverage, incomplete batch failure, model failure stops remaining batches, records and baseline")


if __name__ == "__main__":
    main()
