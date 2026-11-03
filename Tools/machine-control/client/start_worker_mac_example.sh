#!/usr/bin/env bash
set -euo pipefail
# Usage on Mac:
#   CENTRAL_URL=http://10.0.27.95:18765 MACHINE_ID=ios-mac-build-01 TOKEN=dev-token ./start_worker_mac_example.sh
CENTRAL_URL=${CENTRAL_URL:-http://10.0.27.95:18765}
MACHINE_ID=${MACHINE_ID:-ios-mac-build-01}
TOKEN=${TOKEN:-dev-token}
cd "$(dirname "$0")"`nexport PYTHONPATH="$(pwd):$(pwd)/../shared"
echo "================================================================"
echo "Machine Control Worker - macOS"
echo "machine_id     : $MACHINE_ID"
echo "connect server : $CENTRAL_URL"
echo "================================================================"
python3 -m control_worker.client \
  --server "$CENTRAL_URL" \
  --machine-id "$MACHINE_ID" \
  --token "$TOKEN" \
  --capability shell \
  --capability unity \
  --capability xcode \
  --capability ios \
  --allow-command tail \
  --allow-command ls \
  --allow-command cat \
  --allow-command grep \
  --allow-command find \
  --allow-command xcodebuild \
  --allow-command security \
  --allow-command codesign \
  --allow-command plutil \
  --allow-command df \
  --allow-command du



