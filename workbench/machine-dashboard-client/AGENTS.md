# Workbench local client rules

This directory is the client-side companion of the remote workbench. It runs only on the user's computer and may access that computer's storage and child processes. It must not import `machine-dashboard-server`, read the server database, or expose a non-loopback listener.

- `src/local_agent.py` is the HTTP entry point.
- `src/paths.py` owns client-local data, logs and PID paths.
- `src/processes.py` owns local central-client and Codex process lifecycles.
- Browser requests use the explicit `http://127.0.0.1:18991` contract and fail visibly when the agent is unavailable.
- Server paths and server database values must never be returned as client-local paths.
