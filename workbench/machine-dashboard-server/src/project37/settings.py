"""Shared, server-hosted 37 maintenance form settings."""
import json
from contextlib import closing
from core.storage import connect
from .preflight import FIELDS

SETTING_FIELDS = (*FIELDS, "unity_editor")


def get_settings(user_id):
    with closing(connect()) as db:
        row = db.execute("SELECT settings_json FROM project37_shared_settings WHERE id=1").fetchone()
        if row is None:
            row = db.execute("SELECT settings_json FROM project37_settings WHERE user_id=?", (user_id,)).fetchone()
    values = json.loads(row[0]) if row else {}
    return {key: values.get(key, "") for key in SETTING_FIELDS}


def save_settings(user_id, payload):
    if not isinstance(payload, dict) or not set(FIELDS).issubset(payload) or set(payload) - set(SETTING_FIELDS):
        raise ValueError("参数格式不正确")
    values = {}
    for key in SETTING_FIELDS:
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > 4096 or "\0" in value:
            raise ValueError("参数必须是有效的文本")
        values[key] = value.strip()
    with closing(connect()) as db:
        with db:
            db.execute("INSERT INTO project37_shared_settings(id, settings_json) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET settings_json=excluded.settings_json", (json.dumps(values, ensure_ascii=False),))
    return values
