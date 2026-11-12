"""读取和保存本地日志配置。"""
from __future__ import annotations

import json
import platform
import os
import sys
from pathlib import Path
from typing import Any
from dataclasses import dataclass
from enum import IntEnum


def get_user_root() -> Path:
    """返回当前系统的用户数据目录；iOS 使用应用沙盒内目录。"""
    system = platform.system().lower()
    if system in {"ios", "iphoneos", "darwin"} or sys.platform == "ios":
        return Path.home() / "Library" / "Application Support" / "LocalWorkbench"
    if system == "windows":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "LocalWorkbench"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "LocalWorkbench"

# 配置文件仍放在 Infos 目录，settings 模块统一放在 core 下。
SETTING_PATH: Path | None = None
# 用户端设置保存地址，与 storage.CONFIG_PATH 保持一致。
USER_SETTINGS_PATH: Path | None = None
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
DEFAULT_SETTINGS = {"log_level": "INFO", "debug_log": False}


class LogLevel(IntEnum):
    """应用日志级别，数值与 Python logging 保持一致。"""

    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40


@dataclass(frozen=True)
class Settings:
    """应用配置的类型化只读视图。"""

    log_level: str
    debug_log: bool
    output_dir: Path
    log_path: Path
    view_log_path: Path

    @property
    def LOG_LEVEL(self) -> str:
        return self.log_level

    @property
    def DEBUG_LOG(self) -> bool:
        return self.debug_log

    @property
    def OUTPUT_DIR(self) -> Path:
        return self.output_dir

    @property
    def LOG_PATH(self) -> Path:
        return self.log_path

    @property
    def VIEW_LOG_PATH(self) -> Path:
        return self.view_log_path

    @property
    def View_LOG_PATH(self) -> Path:
        return self.view_log_path


def _initialize_paths() -> tuple[Path, Path, dict[str, Any]]:
    """首次使用时按运行平台初始化配置路径和默认值。"""
    global SETTING_PATH, USER_SETTINGS_PATH
    root = get_user_root()
    if SETTING_PATH is None:
        SETTING_PATH = root / "config" / "local_setting.json"
    if USER_SETTINGS_PATH is None:
        USER_SETTINGS_PATH = root / "config" / "settings.json"
    defaults = {
        **DEFAULT_SETTINGS,
        "output_dir": str(root / "output"),
        # SETTING_PATH 所在配置目录下的 logs 子目录。
        "log_path": str(SETTING_PATH.parent / "logs"),
        "view_log_dir": "view",
    }
    return SETTING_PATH, USER_SETTINGS_PATH, defaults


def get_user_settings_path() -> Path:
    """按需初始化并返回用户端配置文件路径。"""
    return _initialize_paths()[1]


def load_local_settings() -> dict[str, Any]:
    """读取本地配置；文件缺失或字段非法时使用默认值。"""
    setting_path, _, defaults = _initialize_paths()
    settings = dict(defaults)
    if setting_path.is_file():
        try:
            loaded = json.loads(setting_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            settings.update(loaded)
    level = str(settings.get("log_level", "INFO")).upper()
    settings["log_level"] = level if level in LOG_LEVELS else "INFO"
    settings["debug_log"] = bool(settings.get("debug_log", False))
    output_dir = Path(str(settings.get("output_dir") or defaults["output_dir"])).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    settings["output_dir"] = str(output_dir)
    log_dir = Path(str(settings.get("log_path") or settings.get("log_dir") or defaults["log_path"])).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    settings["log_path"] = str(log_dir)
    # 兼容 AppLogger 和旧配置的 log_dir 字段。
    settings["log_dir"] = str(log_dir)
    view_log_dir = Path(str(settings.get("view_log_dir") or defaults["view_log_dir"])).expanduser()
    if not view_log_dir.is_absolute():
        view_log_dir = log_dir / view_log_dir
    view_log_dir.mkdir(parents=True, exist_ok=True)
    settings["view_log_dir"] = str(view_log_dir)
    if not setting_path.exists():
        setting_path.parent.mkdir(parents=True, exist_ok=True)
        setting_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings


def get_settings() -> Settings:
    """读取并返回类型化配置对象，供新代码使用。"""
    values = load_local_settings()
    return Settings(
        log_level=values["log_level"],
        debug_log=values["debug_log"],
        output_dir=Path(values["output_dir"]),
        log_path=Path(values["log_path"]),
        view_log_path=Path(values["view_log_dir"]),
    )


def save_local_settings(log_level: str, debug_log: bool, output_dir: str | None = None) -> dict[str, Any]:
    """保存日志等级、调试开关和服务生成文件目录。"""
    level = str(log_level).upper()
    if level not in LOG_LEVELS:
        raise ValueError(f"日志等级必须是 {'、'.join(LOG_LEVELS)}")
    setting_path, _, _ = _initialize_paths()
    current = load_local_settings()
    target = Path(output_dir).expanduser() if output_dir else Path(current["output_dir"])
    target.mkdir(parents=True, exist_ok=True)
    settings = {**current, "log_level": level, "debug_log": bool(debug_log), "output_dir": str(target)}
    setting_path.parent.mkdir(parents=True, exist_ok=True)
    setting_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    return settings
