#!/usr/bin/env bash

# Finder can launch .command files by double-clicking them. Keep this wrapper
# small so the command-line and double-click launch paths share one config.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "Starting Machine Control Worker..."
echo

bash "$SCRIPT_DIR/start_worker_mac_example.sh"
status=$?

echo
if [ "$status" -eq 0 ]; then
  echo "Machine Control Worker has stopped."
else
  echo "Machine Control Worker exited with code $status."
fi
echo "Press Return to close this window."
read -r _

exit "$status"
