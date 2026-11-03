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

The archive is written to `packages/central-client.zip`.
