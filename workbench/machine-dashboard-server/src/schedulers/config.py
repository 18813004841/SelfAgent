"""调度器需要持久化的任务配置。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULT_CONFIG: dict[str, Any] = {"code_review": {"project_path": "", "branch": "", "skill_paths": ["skills"]}}


def load_config() -> dict[str, Any]:
    """读取配置；文件缺失或损坏时恢复默认内容。"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.is_file():
        save_config(DEFAULT_CONFIG)
    try:
        loaded = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        loaded = {}
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if isinstance(loaded, dict):
        for key, value in loaded.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    return config


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def code_review_config() -> dict[str, str]:
    item = load_config().get("code_review", {})
    return {
        "project_path": str(item.get("project_path", "") or ""),
        "branch": str(item.get("branch", "") or ""),
        "skill_paths": item.get("skill_paths", ["skills"]) or ["skills"],
    }


def save_code_review_config(project_path: str, branch: str, skill_paths: list[str] | str = ["skills"]) -> dict[str, Any]:
    config = load_config()
    paths = [x.strip() for x in (skill_paths if isinstance(skill_paths, list) else skill_paths.splitlines()) if str(x).strip()]
    saved = {"project_path": project_path.strip(), "branch": branch.strip(), "skill_paths": paths or ["skills"]}
    config["code_review"] = saved
    save_config(config)
    return saved
