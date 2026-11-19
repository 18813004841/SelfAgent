#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [[ -z "${WORKBENCH_DASHBOARD_URL:-}" ]]; then
  echo "请输入工作台地址，例如 http://192.168.1.10:18888"
  read -r -p "Dashboard URL: " WORKBENCH_DASHBOARD_URL
fi
if [[ ! "$WORKBENCH_DASHBOARD_URL" =~ ^https?://[^/]+(:[0-9]+)?$ ]]; then
  echo "Dashboard URL 必须是工作台网址的来源，不含路径、凭据或查询参数。" >&2
  exit 2
fi

PYTHON="${WORKBENCH_CLIENT_PYTHON:-$ROOT_DIR/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  command -v python3 >/dev/null 2>&1 || { echo "需要安装 Python 3.11 或更新版本。" >&2; exit 1; }
  python3 -m venv "$ROOT_DIR/.venv"
  PYTHON="$ROOT_DIR/.venv/bin/python"
fi

export WORKBENCH_DASHBOARD_URL
export WORKBENCH_CLIENT_PYTHON="$PYTHON"
export WORKBENCH_LOCAL_AGENT_PORT="${WORKBENCH_LOCAL_AGENT_PORT:-18991}"
CONFIG_ROOT="${HOME}/Library/Application Support/LocalWorkbench/config"
STORAGE="${HOME}/Library/Application Support/LocalWorkbench/client/storage"
CONFIG="$CONFIG_ROOT/settings.json"
mkdir -p "$CONFIG_ROOT" "$STORAGE"
if [[ ! -f "$CONFIG" ]]; then
  CONFIG="$CONFIG" STORAGE="$STORAGE" DASHBOARD="$WORKBENCH_DASHBOARD_URL" python3 - <<'PY'
import json, os
path = os.environ["CONFIG"]
data = {"storage_dir": os.environ["STORAGE"], "dashboard_url": os.environ["DASHBOARD"], "local_codex_url": "ws://127.0.0.1:4500", "central_server_url": "", "central_token": "", "machine_id": os.uname().nodename}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(data, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY
fi

exec "$PYTHON" -m src.local_agent --host 127.0.0.1 --port "$WORKBENCH_LOCAL_AGENT_PORT" --dashboard-url "$WORKBENCH_DASHBOARD_URL"
