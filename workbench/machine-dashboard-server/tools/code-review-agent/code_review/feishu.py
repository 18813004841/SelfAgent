"""Optional code-review notifications via a Feishu group bot and lark-cli."""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .models import Finding


def _lookup(email: str) -> tuple[str, str] | None:
    if len(email) > 50 or not re.fullmatch(r"[A-Za-z0-9._+-]+@[A-Za-z0-9.-]+", email):
        return None
    try:
        executable = shutil.which("lark-cli")
        if not executable:
            return None
        result = subprocess.run(
            [executable, "contact", "+search-user", "--query", email, "--as", "user", "--json"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30, check=False,
        )
        data = json.loads(result.stdout)
        if result.returncode or not data.get("ok") or data.get("data", {}).get("has_more"):
            return None
        users = data.get("data", {}).get("users", [])
        matches = [u for u in users if email.casefold() in {str(u.get("email") or "").casefold(), str(u.get("enterprise_email") or "").casefold()} and re.fullmatch(r"ou_[A-Za-z0-9]+", str(u.get("open_id") or ""))]
        if len(matches) != 1:
            return None
        return matches[0]["open_id"], str(matches[0].get("localized_name") or email)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        return None


def notify(findings: list[Finding], threshold: str, webhook: str | None = None, task_name: str | None = None, status: str | None = None) -> list[str]:
    levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    selected = [f for f in findings if levels.get(str(f.severity).lower(), 2) >= levels.get(threshold.lower(), 3)]
    webhook = (os.environ.get("WORKBENCH_CODE_REVIEW_FEISHU_WEBHOOK", "") if webhook is None else webhook).strip()
    if not webhook:
        return ["飞书通知未发送：未配置 WORKBENCH_CODE_REVIEW_FEISHU_WEBHOOK"]
    url = urlsplit(webhook)
    if url.scheme != "https" or url.netloc != "open.feishu.cn" or not url.path.startswith("/open-apis/bot/v2/hook/") or url.query or url.fragment:
        return ["飞书通知未发送：机器人地址格式无效"]
    warnings = []
    users = {}
    for finding in selected:
        email = (finding.author_email or "").strip()
        if email and email not in users:
            users[email] = _lookup(email)
        if not email or not users.get(email):
            warnings.append(f"飞书用户未找到或查询失败：{finding.file}:{finding.line}")
    fallback_email = "bo.feng@funplus.com"
    if any(not users.get((finding.author_email or "").strip()) for finding in selected):
        if fallback_email not in users:
            users[fallback_email] = _lookup(fallback_email)
        if not users[fallback_email]:
            warnings.append("飞书兜底通知人未找到或查询失败：bo.feng@funplus.com")
    lines = ["代码review报告：" + (f"\n任务名：{task_name.strip()}" if task_name and task_name.strip() else "")]
    if status:
        labels = {"passed": "检查完成", "skipped": "没有新提交", "failed": "检查未通过", "error": "检查执行失败", "cancelled": "任务已取消"}
        lines[0] += f"\n检查结果：{labels.get(status, status)}\n问题数量：{len(selected)}"
    for finding in selected:
        user = users.get((finding.author_email or "").strip())
        recipient = user or users.get(fallback_email)
        mention = f'<at user_id="{recipient[0]}">{html.escape(recipient[1])}</at>' if recipient else "（未能匹配通知人）"
        submitter = f"{finding.author or '未知'}（{finding.author_email or '邮箱未知'}）"
        lines.append(f"\n\n{mention}\n提交人：{submitter}\n严重程度：{finding.severity}\n违反规范：{finding.rule or '未提供'}\n问题：{finding.message}\n文件：{finding.file or '未知'}:{finding.line or '?'}\n提交：{finding.commit_sha or '未知'}\n建议：{finding.suggestion or '无'}")
    # Keep individual findings intact when splitting the bot's message limit.
    chunks = []
    current = lines[0]
    for line in lines[1:]:
        if len(line.encode("utf-8")) > 12000:
            warnings.append("飞书通知未发送：单条问题内容过长")
            return warnings
        if len((current + line).encode("utf-8")) > 12000:
            chunks.append(current)
            current = lines[0]
        current += line
    chunks.append(current)
    try:
        for chunk in chunks:
            body = json.dumps({"msg_type": "text", "content": {"text": chunk}}, ensure_ascii=False).encode("utf-8")
            request = Request(webhook, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
            if result.get("code") != 0:
                warnings.append("飞书通知发送失败：机器人接口返回错误")
                break
    except (OSError, URLError, ValueError, TypeError):
        warnings.append("飞书通知发送失败：网络或机器人响应异常")
    return warnings
