import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import time

os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="selfagent-analysis-")
os.environ.setdefault("WORKBENCH_OUTPUT_DIR", str(Path(tempfile.gettempdir()) / "selfagent-analysis-tests"))
os.environ.setdefault("WORKBENCH_LOG_PATH", str(Path(tempfile.gettempdir()) / "selfagent-analysis-tests" / "logs"))
os.environ.setdefault("LOCAL_WORKBENCH_START_TIMESTAMP", "test")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from package_error_analysis import pipeline


class AnalysisGraphTests(unittest.TestCase):
    def run_task(self, path, responses=None):
        task = {"id": "test", "status": "queued", "events": [], "result": {}}
        calls = []
        def request(url, *args, **kwargs):
            calls.append(url)
            return responses[len(calls) - 1]
        with patch.object(pipeline, "_load", return_value=task), patch.object(pipeline, "_save"), \
             patch.object(pipeline, "resolve_jenkins", return_value={}), \
             patch.object(pipeline, "_find_mounted_log", return_value=(path, "mounted:test")), \
             patch.object(pipeline, "_json_request", side_effect=request), \
             patch("integrations.codex_cli.CodexCliClient.execute", return_value=SimpleNamespace(text='{"ok": true, "task_id": "task_test"}')), \
             patch.dict(os.environ, {"MACHINE_CONTROL_CENTER": "http://center", "BUILD_PACKAGE_FAIL_CODEX": "0"}):
            pipeline._run("test", "bundle: 1.2 target_ip: 10.0.0.1 worktree_path: /project")
        return task, calls

    def test_archive_skips_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "build.log"
            path.write_text("SDK initialized\nerror CS1234: test", encoding="utf-8")
            task, calls = self.run_task(path)
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["result"]["failed_step"], "C#编译")
        self.assertEqual(calls, [])
        messages = [event["message"] for event in task["events"]]
        for label in ("解析输入和补全参数", "读取归档日志", "分析日志", "保存分析结果"):
            self.assertTrue(any(message.startswith(label + "：开始") for message in messages))
            self.assertTrue(any(message.startswith(label + "：结束") for message in messages))
        self.assertTrue(any("读取打包机日志：已跳过" in message for message in messages))
        self.assertTrue(messages[-1].startswith("保存分析结果：结束"))

    def test_missing_and_empty_archive_fall_back_to_worker(self):
        responses = [
            {"task": {"task_id": "task_test", "machine_id": "worker", "kind": "read_build_log", "created_at": int(time.time()*1000), "payload": {"worktree_path": "/project", "relative_path": "Game/BuildFolder/BuildTemporary/Unity.log"}, "status": "succeeded", "result": {"ok": True, "text": "error CS1234: test"}}},
            {"workers": [{"machine_id": "worker", "meta": {"local_ips": ["10.0.0.1"]}}]},
        ]
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty.log"
            empty.write_text("", encoding="utf-8")
            for path in (None, empty):
                with self.subTest(path=path):
                    task, calls = self.run_task(path, responses)
                    self.assertEqual(task["status"], "completed")
                    self.assertEqual(len(calls), 2)
                    self.assertTrue(any("使用在线 Worker" in event["message"] for event in task["events"]))

    def test_no_log_fails_task(self):
        task, _ = self.run_task(None, [{"workers": []}])
        self.assertEqual(task["status"], "failed")
        self.assertIn("通过 Codex 和中央服务器 MCP", task["error"])
        self.assertTrue(any("读取打包机日志：结束，执行失败" in event["message"] for event in task["events"]))

    def test_rejects_mismatched_remote_task(self):
        responses = [
            {"task": {"task_id": "task_test", "machine_id": "other", "kind": "read_build_log", "created_at": int(time.time()*1000), "payload": {"worktree_path": "/project", "relative_path": "Game/BuildFolder/BuildTemporary/Unity.log"}, "status": "succeeded", "result": {"ok": True, "text": "wrong log"}}},
            {"workers": [{"machine_id": "worker", "meta": {"local_ips": ["10.0.0.1"]}}]},
        ]
        task, _ = self.run_task(None, responses)
        self.assertEqual(task["status"], "failed")
        self.assertFalse(task["result"])

    def test_parse_quoted_windows_worktree(self):
        info = pipeline.parse_input('target_ip: 10.0.0.1 worktree_path: "C:\\Build Jobs\\Game"')
        self.assertEqual(info["worktree_path"], "C:\\Build Jobs\\Game")

    def test_no_failure_signal_is_not_diagnosed_as_sdk(self):
        result = pipeline._analyse_log("SDK initialized\nGradle started", {})
        self.assertEqual(result["failed_step"], "未识别")


if __name__ == "__main__":
    unittest.main()
