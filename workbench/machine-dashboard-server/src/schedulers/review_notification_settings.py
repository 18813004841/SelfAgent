"""Server-local code-review notification credentials."""
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from core.settings import get_user_root


def _path() -> Path:
    return get_user_root() / "config" / "code-review-notification.json"


def get_webhook() -> str:
    path = _path()
    if not path.exists():
        return os.environ.get("WORKBENCH_CODE_REVIEW_FEISHU_WEBHOOK", "").strip()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("webhook"), str):
            raise ValueError
        return value["webhook"]
    except (OSError, ValueError):
        raise ValueError("无法读取飞书通知配置") from None


def save_webhook(value: str) -> None:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("飞书通知地址格式无效")
    value = value.strip()
    try:
        url = urlsplit(value)
        valid = not value or (url.scheme == "https" and url.netloc == "open.feishu.cn" and url.path.startswith("/open-apis/bot/v2/hook/") and bool(url.path.removeprefix("/open-apis/bot/v2/hook/")) and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("飞书通知地址格式无效")
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".code-review-notification-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump({"webhook": value}, output, ensure_ascii=False)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)
