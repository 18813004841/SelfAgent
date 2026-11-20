#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

# Prefer an explicitly configured origin, then the saved client configuration.
# Never guess from the client's own LAN address: the workbench may run on a
# different machine on the same network.
if [[ -z "${WORKBENCH_DASHBOARD_URL:-}" ]]; then
  CONFIG_FILE="$HOME/Library/Application Support/LocalWorkbench/config/settings.json"
  if [[ -f "$CONFIG_FILE" ]]; then
    WORKBENCH_DASHBOARD_URL="$(CONFIG_FILE="$CONFIG_FILE" python3 - <<'PY'
import json, os
try:
    with open(os.environ["CONFIG_FILE"], encoding="utf-8-sig") as handle:
        value = json.load(handle)
    print(value.get("dashboard_url", "") if isinstance(value, dict) else "")
except (OSError, ValueError):
    print("")
PY
)"
  fi
fi
WORKBENCH_DASHBOARD_URL="${WORKBENCH_DASHBOARD_URL:-http://127.0.0.1:18888}"
# Strip Markdown link syntax when a URL was copied from the workbench message.
MARKDOWN_URL_RE='^\[([^]]+)\]\((https?://[^)]+)\)$'
if [[ "$WORKBENCH_DASHBOARD_URL" =~ $MARKDOWN_URL_RE ]]; then
  WORKBENCH_DASHBOARD_URL="${BASH_REMATCH[2]}"
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

# Restart only an existing Local Agent owned by this project. Never kill an
# unrelated process that happens to use the same port.
if command -v lsof >/dev/null 2>&1; then
  EXISTING_PID="$(lsof -tiTCP:"$WORKBENCH_LOCAL_AGENT_PORT" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
  if [[ -n "$EXISTING_PID" ]]; then
    EXISTING_COMMAND="$(ps -p "$EXISTING_PID" -o command= 2>/dev/null || true)"
    if [[ "$EXISTING_COMMAND" == *"src.local_agent"* && "$EXISTING_COMMAND" == *"--port $WORKBENCH_LOCAL_AGENT_PORT"* ]]; then
      echo "检测到已有 Local Agent (PID $EXISTING_PID)，正在停止并重新启动..."
      kill "$EXISTING_PID" 2>/dev/null || true
      for _ in {1..20}; do
        kill -0 "$EXISTING_PID" 2>/dev/null || break
        sleep 0.1
      done
      if kill -0 "$EXISTING_PID" 2>/dev/null; then
        kill -KILL "$EXISTING_PID" 2>/dev/null || true
      fi
    else
      echo "端口 127.0.0.1:$WORKBENCH_LOCAL_AGENT_PORT 已被其他进程占用，未执行清理。" >&2
      exit 1
    fi
  fi
fi
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
