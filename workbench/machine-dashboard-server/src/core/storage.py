"""本地工作台持久化辅助模块。

集中管理用户级配置目录，以及工具、定时任务和执行记录使用的 SQLite
数据库。支持通过 ``LOCALAPPDATA`` 覆盖路径，便于测试和便携式启动。
"""

import json, os, sqlite3
from pathlib import Path

# 仓库内资源，例如调度器 PID 文件。
ROOT = Path(__file__).resolve().parents[2]
# 用户级状态。生产环境默认位于 %LOCALAPPDATA%\\LocalWorkbench，测试时可覆盖。
USER_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "LocalWorkbench"
PID_PATH = ROOT / "data" / "scheduler.pid"
CONFIG_PATH = USER_ROOT / "config" / "settings.json"
DB_PATH = USER_ROOT / "data" / "scheduler.db"

def default_settings():
    """返回用户尚未配置存储路径时使用的默认设置。"""
    return {"storage_dir": str(USER_ROOT / "storage")}

def get_settings():
    """读取设置；首次使用时创建默认设置文件。"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_settings(default_settings())
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def save_settings(settings):
    """保存设置，并确保配置的存储目录已经存在。"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(settings["storage_dir"]).mkdir(parents=True, exist_ok=True)

def connect():
    """打开调度器数据库并执行兼容式结构迁移。

    工作台和独立调度器进程可能同时读写任务状态，因此启用 WAL 模式。
    迁移只增加带默认值的字段，保证已有安装可以继续使用。
    """
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
    # 为任务进度和取消操作增加字段；已有安装启动时自动获得新字段。
    for statement in (
        "ALTER TABLE schedules ADD COLUMN task_type TEXT NOT NULL DEFAULT 'scheduled'",
        "ALTER TABLE schedules ADD COLUMN progress_current INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE schedules ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE schedules ADD COLUMN cancel_requested INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE schedules ADD COLUMN dispatcher TEXT NOT NULL DEFAULT 'scheduler'",
    ):
        try: db.execute(statement)
        except sqlite3.OperationalError:
            pass
    db.commit()
    return db

def row_json(row):
    """将 SQLite 行转换为普通字典，并保留 None 值。"""
    return dict(row) if row else None

def decode_schedule(row):
    """解析定时任务记录，并反序列化其中的 JSON 参数。"""
    item = row_json(row)
    if item: item["args"] = json.loads(item.pop("args_json", "{}"))
    return item
