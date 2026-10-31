import json, os, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "LocalWorkbench"
PID_PATH = ROOT / "data" / "scheduler.pid"
CONFIG_PATH = USER_ROOT / "config" / "settings.json"
DB_PATH = USER_ROOT / "data" / "scheduler.db"

def default_settings():
    return {"storage_dir": str(USER_ROOT / "storage")}

def get_settings():
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_settings(default_settings())
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def save_settings(settings):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(settings["storage_dir"]).mkdir(parents=True, exist_ok=True)

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS tools (
      tool_id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
      entry TEXT NOT NULL, workdir TEXT, enabled INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS schedules (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, tool_id TEXT NOT NULL,
      schedule_type TEXT NOT NULL, schedule_expr TEXT NOT NULL,
      args_json TEXT NOT NULL DEFAULT '{}', timeout INTEGER NOT NULL DEFAULT 300,
      retry INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
      next_run REAL, last_run REAL, last_status TEXT, last_error TEXT,
      FOREIGN KEY(tool_id) REFERENCES tools(tool_id)
    );
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT, schedule_id TEXT NOT NULL,
      started_at REAL NOT NULL, finished_at REAL, status TEXT NOT NULL,
      output TEXT, error TEXT
    );
    """)
    return db

def row_json(row):
    return dict(row) if row else None

def decode_schedule(row):
    item = row_json(row)
    if item: item["args"] = json.loads(item.pop("args_json", "{}"))
    return item
