#!/usr/bin/env bash

# macOS Finder launcher for the Machine Control Center in LAN mode.
# Optional overrides: CENTER_PORT=18765 CENTER_TOKEN=dev-token

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
export PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/../shared" || exit 1

CENTER_HOST="${CENTER_HOST:-0.0.0.0}"
CENTER_PORT="${CENTER_PORT:-18765}"
CENTER_TOKEN="${CENTER_TOKEN:-dev-token}"

LAN_IP=""
for interface in en0 en1 en2 en3 en4 en5; do
  LAN_IP="$(ipconfig getifaddr "$interface" 2>/dev/null || true)"
  if [ -n "$LAN_IP" ]; then
    break
  fi
done

echo "================================================================"
echo "Machine Control Center - LAN mode (macOS)"
echo "Listen URL for local machine : http://127.0.0.1:${CENTER_PORT}"
if [ -n "$LAN_IP" ]; then
  echo "Listen URL for LAN workers   : http://${LAN_IP}:${CENTER_PORT}"
else
  echo "Listen URL for LAN workers   : http://<this-mac-lan-ip>:${CENTER_PORT}"
fi
echo "Token                        : ${CENTER_TOKEN}"
echo "================================================================"
echo

python3 -m control_center.server \
  --host "$CENTER_HOST" \
  --port "$CENTER_PORT" \
  --token "$CENTER_TOKEN"
status=$?

echo
if [ "$status" -eq 0 ]; then
  echo "Central LAN server has stopped."
else
  echo "Central LAN server exited with code $status."
fi
echo "Press Return to close this window."
read -r _

exit "$status"


