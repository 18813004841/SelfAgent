from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict

from control_mcp.client import ControlCenterClient

MCP_IMPORT_ERROR = None
try:
    from mcp.server.fastmcp import FastMCP
except Exception as e:  # pragma: no cover
    try:
        # MCP 2.x renamed FastMCP to MCPServer while retaining the tool/run
        # surface used below. Keep the adapter here so the optional extra can
        # follow its lockfile without forcing a legacy mcp<2 pin.
        from mcp.server.mcpserver import MCPServer as FastMCP
    except Exception:
        FastMCP = None
        MCP_IMPORT_ERROR = e
else:
    MCP_IMPORT_ERROR = None


def build_mcp(server_url: str, token: str, *, log_target: str = "", log_worktree: str = ""):
    if FastMCP is None:
        raise RuntimeError(f"mcp package not available: {MCP_IMPORT_ERROR!r}")
    client = ControlCenterClient(server_url, token)
    mcp = FastMCP("machine-control")

    if log_target or log_worktree:
        if not log_target or not log_worktree:
            raise ValueError("target and worktree are both required")
        submitted = None

        @mcp.tool()
        def submit_build_log() -> Dict[str, Any]:
            """Submit the single preconfigured build-log read and return its task ID."""
            nonlocal submitted
            if submitted is not None:
                return submitted
            workers = client.list_workers().get("workers", [])
            now_ms = time.time() * 1000
            matched = [w for w in workers if w.get("status") == "online"
                       and log_target in (w.get("meta", {}).get("local_ips", []) or [])
                       and 0 <= now_ms - float(w.get("last_seen_at", 0)) <= 60000]
            if len(matched) != 1:
                return {"ok": False, "error": "目标 IP 未匹配到唯一且最近在线的 Worker"}
            response = client.submit_build_log(matched[0]["machine_id"], log_worktree)
            task_id = response.get("task", {}).get("task_id")
            if not task_id:
                return {"ok": False, "error": "中央服务器未返回任务 ID"}
            submitted = {"ok": True, "task_id": task_id}
            return submitted

        return mcp

    @mcp.tool()
    def health() -> Dict[str, Any]:
        """Check whether the central machine-control server is reachable."""
        return client.health()

    @mcp.tool()
    def list_workers() -> Dict[str, Any]:
        """List registered workers and their capabilities/status."""
        return client.list_workers()

    @mcp.tool()
    def list_tasks() -> Dict[str, Any]:
        """List known tasks, newest first."""
        return client.list_tasks()

    @mcp.tool()
    def get_task(task_id: str) -> Dict[str, Any]:
        """Get one task status and result by task_id."""
        return client.get_task(task_id)

    @mcp.tool()
    def submit_shell_task(machine_id: str, command: str, timeout: int = 60, cwd: str = "") -> Dict[str, Any]:
        """Submit a shell command task to one worker. Command is checked by the worker allowlist."""
        return client.submit_shell_task(machine_id, command, timeout, cwd or None)

    @mcp.tool()
    def submit_shell_task_and_wait(machine_id: str, command: str, timeout: int = 60, cwd: str = "") -> Dict[str, Any]:
        """Submit a shell command task and wait for completion."""
        created = client.submit_shell_task(machine_id, command, timeout, cwd or None)
        task_id = created["task"]["task_id"]
        return client.wait_task(task_id, timeout=timeout + 30)

    return mcp


def fallback_cli(server_url: str, token: str, argv: list[str]) -> int:
    """Small non-MCP CLI for local verification and debugging."""
    c = ControlCenterClient(server_url, token)
    if not argv or argv[0] == "health":
        print(json.dumps(c.health(), ensure_ascii=False, indent=2))
        return 0
    if argv[0] == "list-workers":
        print(json.dumps(c.list_workers(), ensure_ascii=False, indent=2))
        return 0
    if argv[0] == "list-tasks":
        print(json.dumps(c.list_tasks(), ensure_ascii=False, indent=2))
        return 0
    if argv[0] == "submit-shell":
        if len(argv) < 3:
            raise SystemExit("usage: submit-shell <machine_id> <command>")
        print(json.dumps(c.submit_shell_task(argv[1], argv[2]), ensure_ascii=False, indent=2))
        return 0
    raise SystemExit(f"unknown fallback command: {argv[0]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=os.getenv("MACHINE_CONTROL_URL", "http://127.0.0.1:18765"))
    parser.add_argument("--token", default=os.getenv("MACHINE_CONTROL_TOKEN", "dev-token"))
    parser.add_argument("--fallback-cli", action="store_true", help="Run a simple verification CLI instead of MCP stdio server")
    parser.add_argument("args", nargs="*")
    args = parser.parse_args()
    if args.fallback_cli:
        raise SystemExit(fallback_cli(args.server, args.token, args.args))
    mcp = build_mcp(args.server, args.token, log_target=os.environ.get("MACHINE_CONTROL_LOG_TARGET", ""),
                    log_worktree=os.environ.get("MACHINE_CONTROL_LOG_WORKTREE", ""))
    mcp.run()


if __name__ == "__main__":
    main()
