#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif [ -x ".venv/Scripts/python.exe" ]; then
  PYTHON=".venv/Scripts/python.exe"
else
  PYTHON="${MACHINE_DASHBOARD_PYTHON:-python3}"
fi
export PYTHONPATH="${PYTHONPATH:-src}"
export MACHINE_DASHBOARD_HOST="${MACHINE_DASHBOARD_HOST:-0.0.0.0}"
export MACHINE_DASHBOARD_PORT="${MACHINE_DASHBOARD_PORT:-18888}"
exec "$PYTHON" src/server.py
