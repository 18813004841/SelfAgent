#!/usr/bin/env python3
"""隔离验证工作台 SQLite 初始化、迁移、备份和完整性。"""
from __future__ import annotations
import os
import sqlite3
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix="selfagent-storage-"))
os.environ["LOCALAPPDATA"] = str(root)
os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "workbench" / "machine-dashboard-server" / "src")
import sys
sys.path.insert(0, os.environ["PYTHONPATH"])
from core import storage

with storage.connect() as db:
    db.execute("INSERT INTO tools(tool_id,name,type,entry) VALUES(?,?,?,?)", ("verify", "verify", "cli", "noop"))
    db.commit()
db.close()
assert storage.check_database()
backup = storage.backup_database()
assert backup and backup.exists()
with sqlite3.connect(backup) as db:
    assert db.execute("SELECT name FROM tools WHERE tool_id='verify'").fetchone()[0] == "verify"
# 模拟数据库损坏，再用在线备份恢复到原路径；所有连接必须先关闭。
db.close()
storage.DB_PATH.write_bytes(b"damaged database")
for suffix in ("-wal", "-shm"):
    Path(str(storage.DB_PATH) + suffix).unlink(missing_ok=True)
assert storage.check_database() is False, "corrupt database must be detected"
storage.DB_PATH.unlink()
with sqlite3.connect(backup) as source, sqlite3.connect(storage.DB_PATH) as restored:
    source.backup(restored)
assert storage.check_database()
with storage.connect() as db:
    assert db.execute("SELECT name FROM tools WHERE tool_id='verify'").fetchone()[0] == "verify"
db.close()
with sqlite3.connect(storage.DB_PATH) as db:
    db.execute("PRAGMA user_version=99")
try:
    storage.connect()
except sqlite3.DatabaseError:
    pass
else:
    raise AssertionError("newer schema version must be rejected")
print(f"storage validation passed: {storage.DB_PATH}")
