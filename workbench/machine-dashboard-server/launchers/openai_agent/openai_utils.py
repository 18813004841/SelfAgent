"""OpenAI-compatible gateway helpers used by the workbench launcher."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://10.0.27.224:8317/v1"
CONFIG_PATH = Path(__file__).with_name("shared_pool.local.json")

logger = logging.getLogger("openai-agent.chat")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    log_path = Path(__file__).resolve().parents[3] / "logs" / "openai-chat.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [openai_agent] %(levelname)s %(message)s"))
    logger.addHandler(handler)


def load_shared_pool() -> tuple[str, str]:
    """Load the shared-pool address and key without embedding the secret."""
    base_url = os.getenv("SHARED_POOL_BASE_URL", DEFAULT_BASE_URL)
    api_key = os.getenv("SHARED_POOL_API_KEY", "")
    if CONFIG_PATH.is_file():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        base_url = str(data.get("base_url") or base_url)
        api_key = str(data.get("api_key") or api_key)
    return base_url.rstrip("/"), api_key.strip()


def create_model(
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
) -> "GatewayModel":
    """Create a client for the shared OpenAI-compatible Responses pool."""
    configured_url, configured_key = load_shared_pool()
    resolved_key = (api_key or configured_key).strip()
    if not resolved_key:
        raise RuntimeError(
            "未配置共享池 API Key。请写入 "
            f"{CONFIG_PATH} 的 api_key，或设置环境变量 SHARED_POOL_API_KEY。"
        )
    return GatewayModel(
        model=model,
        base_url=(base_url or configured_url).rstrip("/"),
        api_key=resolved_key,
    )


class GatewayModel:
    def __init__(self, model: str, base_url: str, api_key: str) -> None:
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    def invoke(self, message: str | list[dict[str, Any]]) -> str:
        messages = [{"role": "user", "content": message}] if isinstance(message, str) else message
        payload = {"model": self.model, "input": messages, "stream": False, "store": False}
        logger.info(
            "request model=%s url=%s messages=%d content_length=%d",
            self.model, self.base_url, len(messages), len(str(message)),
        )
        try:
            status, body = self._post(payload)
            if status == 400 and "Stream must be set to true" in body:
                payload["stream"] = True
                status, body = self._post(payload)
            if status >= 400:
                raise RuntimeError(f"共享池请求失败 ({status}): {body[:500]}")
            result = _extract_text(body)
            logger.info("response parsed content_length=%d", len(result))
            return result
        except Exception:
            logger.exception("request failed model=%s url=%s", self.model, self.base_url)
            raise

    def _post(self, payload: dict[str, Any]) -> tuple[int, str]:
        request = urllib.request.Request(
            f"{self.base_url}/responses",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream, application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")


def _extract_text(body: str) -> str:
    stripped = body.lstrip()
    if stripped.startswith(("data:", "event:")):
        parts: list[str] = []
        for line in body.splitlines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            event = json.loads(raw)
            if event.get("type") == "response.output_text.delta" and isinstance(event.get("delta"), str):
                parts.append(event["delta"])
            elif event.get("type") == "response.output_text.done" and isinstance(event.get("text"), str):
                return event["text"]
        if parts:
            return "".join(parts)
        raise RuntimeError(f"共享池流式响应没有文本: {body[:500]}")
    data = json.loads(body)
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    texts: list[str] = []
    for item in data.get("output") or []:
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
    if texts:
        return "".join(texts)
    raise RuntimeError(f"共享池返回格式无效: {body[:500]}")


def send_message(message: str, model: str = "gpt-5.6-terra", base_url: str | None = None) -> str:
    """Create a model and send one message."""
    return create_model(model, base_url).invoke(message)
