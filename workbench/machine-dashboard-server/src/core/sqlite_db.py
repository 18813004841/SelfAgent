"""调度器 SQLite 的通用增删改查。"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .storage import connect, row_json

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SqliteDB:
    """封装定时任务数据库的插入、查询、更新和删除。"""

    def __init__(self):
        # 复用 storage.connect，保证表结构和字段迁移只维护一处。
        self.db = connect()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "SqliteDB":
        return self

    def __exit__(self, *_args: Any) -> None:
        # 支持 with SqliteDB() as db，离开代码块时自动关闭连接。
        self.close()

    @staticmethod
    def _name(value: str) -> str:
        # 表名和字段名不能参数化，先限制为普通标识符，避免拼接 SQL。
        if not _NAME.fullmatch(value):
            raise ValueError(f"非法标识符: {value}")
        return value

    def insert(self, table: str, data: Mapping[str, Any]) -> int:
        """插入一行并返回自增主键；无自增主键时返回 0。"""
        table = self._name(table)
        columns = [self._name(key) for key in data]
        # 字段值全部使用占位符绑定，不把业务数据拼进 SQL。
        sql = f"INSERT INTO {table}({','.join(columns)}) VALUES({','.join('?' for _ in columns)})"
        cursor = self.db.execute(sql, tuple(data.values()))
        self.db.commit()
        return int(cursor.lastrowid or 0)

    def query(self, table: str, where: str = "", params: Sequence[Any] = (), order: str = "", limit: int | None = None) -> list[dict[str, Any]]:
        """按条件查询多行。where 和 order 只允许调用方传入受控 SQL 片段。"""
        sql = f"SELECT * FROM {self._name(table)}"
        if where:
            sql += f" WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        # Row 转成普通字典，调用方不需要依赖 sqlite3.Row。
        return [row_json(row) for row in self.db.execute(sql, tuple(params))]

    def get(self, table: str, column: str, value: Any) -> dict[str, Any] | None:
        """按单个字段读取一行。"""
        rows = self.query(table, f"{self._name(column)}= ?", (value,), limit=1)
        return rows[0] if rows else None

    def update(self, table: str, data: Mapping[str, Any], where: str, params: Sequence[Any] = ()) -> int:
        """按条件更新，返回受影响行数。"""
        table = self._name(table)
        columns = [self._name(key) for key in data]
        sql = f"UPDATE {table} SET {','.join(f'{column}=?' for column in columns)} WHERE {where}"
        cursor = self.db.execute(sql, (*data.values(), *params))
        self.db.commit()
        # rowcount 为本次条件命中的行数，0 表示没有匹配记录。
        return cursor.rowcount

    def delete(self, table: str, where: str, params: Sequence[Any] = ()) -> int:
        """按条件删除，返回受影响行数。"""
        cursor = self.db.execute(f"DELETE FROM {self._name(table)} WHERE {where}", tuple(params))
        self.db.commit()
        return cursor.rowcount
