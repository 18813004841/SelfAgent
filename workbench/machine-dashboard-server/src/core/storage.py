"""本地工作台持久化辅助模块。

集中管理用户级配置目录，以及工具、定时任务和执行记录使用的 SQLite
数据库。支持通过 ``LOCALAPPDATA`` 覆盖路径，便于测试和便携式启动。
"""

import json, os, sqlite3
from datetime import datetime
from contextlib import closing
from pathlib import Path
from .settings import get_user_root, get_user_settings_path

# 用户级状态。生产环境默认位于 %LOCALAPPDATA%\\LocalWorkbench，测试时可覆盖。
USER_ROOT = get_user_root()
RUN_DIR = USER_ROOT / "run"
PID_PATH = RUN_DIR / "scheduler.pid"
CENTER_PID_PATH = RUN_DIR / "central-server.pid"
DB_PATH = USER_ROOT / "data" / "scheduler.db"
MACHINE_CONTROL_STORE_PATH = USER_ROOT / "data" / "machine-control" / "control-center.json"

def default_settings():
    """返回用户尚未配置存储路径时使用的默认设置。"""
    return {"storage_dir": str(USER_ROOT / "storage")}

def get_settings():
    """读取设置；首次使用时创建默认设置文件。"""
    CONFIG_PATH = get_user_settings_path()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_settings(default_settings())
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def save_settings(settings):
    """保存设置，并确保配置的存储目录已经存在。"""
    CONFIG_PATH = get_user_settings_path()
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(settings["storage_dir"]).mkdir(parents=True, exist_ok=True)

def backup_database() -> Path | None:
    """在打开迁移前创建数据库副本；没有数据库时返回 None。"""
    if not DB_PATH.is_file():
        return None
    backup_dir = USER_ROOT / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"scheduler-{datetime.now():%Y%m%d_%H%M%S_%f}.db"
    # SQLite backup 包含 WAL 中已提交的数据，不能直接复制主数据库文件。
    source = sqlite3.connect(DB_PATH, timeout=10)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


def check_database() -> bool:
    """执行 SQLite 完整性检查，失败时返回 False。"""
    if not DB_PATH.is_file():
        return True
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=5)) as db:
            return db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.DatabaseError:
        return False


def connect():
    """打开调度器数据库并执行兼容式结构迁移。

    工作台和独立调度器进程可能同时读写任务状态，因此启用 WAL 模式。
    迁移只增加带默认值的字段，保证已有安装可以继续使用。
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > 1:
        db.close()
        raise sqlite3.DatabaseError("Database schema is newer than this application")
    if version == 0:
        backup_database()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
      password_hash TEXT NOT NULL, display_name TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0,
      enabled INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS user_permissions (
      user_id INTEGER NOT NULL, module_key TEXT NOT NULL,
      PRIMARY KEY(user_id, module_key), FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS sessions (
      token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      expires_at TEXT NOT NULL, last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
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
    CREATE TABLE IF NOT EXISTS local_codex_tasks (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, cwd TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'idle', prompt TEXT NOT NULL DEFAULT '',
      messages_json TEXT NOT NULL DEFAULT '[]', log TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS server_maintenance_session (
      id INTEGER PRIMARY KEY CHECK (id=1), session_id TEXT,
      messages_json TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'idle',
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # 为任务进度和取消操作增加字段；已有安装启动时自动获得新字段。
    migrate_roles = "role" not in {r[1] for r in db.execute("PRAGMA table_info(users)")}
    for statement in (
        "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'",
        "ALTER TABLE schedules ADD COLUMN task_type TEXT NOT NULL DEFAULT 'scheduled'",
        "ALTER TABLE schedules ADD COLUMN progress_current INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE schedules ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE schedules ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE schedules ADD COLUMN dispatcher TEXT NOT NULL DEFAULT 'scheduler'",
        "ALTER TABLE schedules ADD COLUMN scheduler_type TEXT",
        "ALTER TABLE schedules ADD COLUMN run_type INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE schedules ADD COLUMN run_time TEXT",
        "ALTER TABLE schedules ADD COLUMN param_json TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE local_codex_tasks ADD COLUMN session_id TEXT",
        "ALTER TABLE local_codex_tasks ADD COLUMN skill_paths_json TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE local_codex_tasks ADD COLUMN allow_extra_rules INTEGER NOT NULL DEFAULT 0",
    ):
        try:
            db.execute(statement)
        except sqlite3.OperationalError as exc:
            # 仅允许“字段已存在”的兼容启动；锁、磁盘和其他错误必须暴露。
            if "duplicate column name" not in str(exc).lower():
                db.rollback()
                raise
    db.execute("PRAGMA user_version=1")
    if migrate_roles:
        db.execute("UPDATE users SET role='admin' WHERE is_admin=1")
        db.execute("UPDATE users SET role='developer' WHERE is_admin=0 AND role='user' AND EXISTS (SELECT 1 FROM user_permissions p WHERE p.user_id=users.id AND p.module_key IN ('central-server','openai-agent'))")
        db.execute("UPDATE users SET role='advanced' WHERE is_admin=0 AND role='user' AND EXISTS (SELECT 1 FROM user_permissions p WHERE p.user_id=users.id AND p.module_key IN ('scheduler','code-review'))")
    db.commit()
    return db

def row_json(row):
    """将 SQLite 行转换为普通字典，并保留 None 值。"""
    return dict(row) if row else None

def decode_schedule(row):
    """解析定时任务记录，并反序列化其中的 JSON 参数。"""
    item = row_json(row)
    if item:
        item["args"] = json.loads(item.get("args_json", "{}"))
        item["param"] = json.loads(item.get("param_json", "{}") or "{}")
        item["scheduler_type"] = item.get("scheduler_type") or item.get("dispatcher") or item.get("tool_id")
        item["run_type"] = int(item.get("run_type") or (1 if item.get("schedule_type") == "daily" else 2))
        item["run_time"] = item.get("run_time") or item.get("schedule_expr")
    return item
