import sys, time
from pathlib import Path
from unittest.mock import patch
root = Path(__file__).resolve().parents[1] / "Tools" / "machine-control"
sys.path[:0] = [str(root / "server"), str(root / "shared")]
from control_mcp.server import build_mcp
from control_mcp.client import ControlCenterClient

now = int(time.time() * 1000)
worker = {"machine_id":"worker-1", "status":"online", "last_seen_at":now, "meta":{"local_ips":["10.0.0.1"]}}
with patch.object(ControlCenterClient, "list_workers", return_value={"workers":[worker]}), patch.object(ControlCenterClient, "submit_build_log", return_value={"task":{"task_id":"task_123"}}) as submit:
    mcp = build_mcp("http://localhost", "test", log_target="10.0.0.1", log_worktree="C:/project")
    tools = mcp._tool_manager.list_tools()
    assert [t.name for t in tools] == ["submit_build_log"]
    assert tools[0].fn() == {"ok":True,"task_id":"task_123"}
    assert tools[0].fn()["task_id"] == "task_123"
    submit.assert_called_once_with("worker-1", "C:/project")
with patch.object(ControlCenterClient, "list_workers", return_value={"workers":[worker, worker]}), patch.object(ControlCenterClient, "submit_build_log") as submit:
    tool = build_mcp("http://localhost", "test", log_target="10.0.0.1", log_worktree="C:/project")._tool_manager.list_tools()[0]
    assert tool.fn()["ok"] is False
    submit.assert_not_called()
print("restricted MCP catalog, unique worker, bounded request and duplicate protection passed")
