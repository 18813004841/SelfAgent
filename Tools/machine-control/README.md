# Machine control layout

- `server/`: central server (`control_center`) and server launchers.
- `client/`: worker client (`control_worker`), local process manager package, and client launchers.
- `shared/`: code shared by server and client (`common`).
- `scripts/`: diagnostics, task helpers, and client package builder.
- `data/`: central server runtime state.
- `logs/`: central server runtime logs.

Build a downloadable client package with:

```powershell
python scripts/build_client_package.py
```

Build the Python distribution without writing build metadata into the source
tree with:

```powershell
python scripts/build_python_package.py --output-dir <temporary-directory>
```

The archive is written to `packages/central-client.zip`. Both the ZIP and the
expanded `packages/central-client/` staging directory are generated outputs and
are ignored by Git. Use `--output-dir <temporary-directory>` for CI or validation
so the source tree is not modified.

Task cancellation: authenticated `POST /api/tasks/{id}/cancel` cancels queued tasks
and persists their terminal status. Repeated requests for terminal tasks are
idempotent. For running tasks it records `cancel_requested` and returns HTTP 202;
the Worker polls that state, terminates its owned subprocess, and reports terminal
`cancelled`. Late results cannot overwrite a terminal state. If process-tree
cleanup fails, the Worker reports `failed` with `cleanup_error` so callers do
not mistake an unverified termination for a successful cancellation.
The Python `ControlCenterClient.cancel_task(task_id)` method is the supported
client wrapper for this endpoint.

After `uv sync --locked --extra mcp`, validate the real stdio handshake and tool
catalog with `.venv/Scripts/python.exe ../../scripts/validate_machine_control_mcp.py`
(use `.venv/bin/python` on Unix). This optional regression requires MCP installed;
it executes only isolated `echo` and an intentionally rejected command against
temporary services, never production data.
