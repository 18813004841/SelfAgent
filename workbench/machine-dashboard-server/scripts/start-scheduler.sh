#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
PYTHON=".venv/Scripts/python.exe"
[ -x "$PYTHON" ] || PYTHON=python3
PYTHONPATH=src exec "$PYTHON" src/scheduler.py
