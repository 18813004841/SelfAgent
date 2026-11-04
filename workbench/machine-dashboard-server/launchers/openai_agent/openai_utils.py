"""OpenAI-compatible gateway helpers used by the workbench launcher."""
from __future__ import annotations

import json
import logging
from pathlib import Path
import urllib.request
from typing import Any


DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765/v1"

logger = logging.getLogger("openai-agent.chat")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    log_path = Path(__file__).resolve().parents[3] / "logs" / "openai-chat.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [openai_agent] %(levelname)s %(message)s"))
    logger.addHandler(handler)


def create_model(model: str, base_url: str = DEFAULT_GATEWAY_URL) -> "GatewayModel":
    """Create a lightweight model client without importing the Agent project."""
    return GatewayModel(model=model, base_url=base_url.rstrip("/"))


class GatewayModel:
    def __init__(self, model: str, base_url: str) -> None:
        self.model = model
        self.base_url = base_url

    def invoke(self, message: str | list[dict[str, Any]]) -> str:
        messages = [{"role": "user", "content": message}] if isinstance(message, str) else message
        payload = {"model": self.model, "messages": messages}
        logger.info("request model=%s url=%s messages=%d content_length=%d", self.model, self.base_url, len(messages), len(str(message)))
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                logger.info("response status=%s headers=%s", response.status, dict(response.headers))
                data = json.load(response)
        except Exception:
            logger.exception("request failed model=%s url=%s", self.model, self.base_url)
            raise
        try:
            result = str(data["choices"][0]["message"].get("content") or "")
            logger.info("response parsed content_length=%d", len(result))
            return result
        except (KeyError, IndexError, TypeError) as exc:
            logger.exception("invalid gateway response data=%r", data)
            raise RuntimeError(f"网关返回格式无效: {data!r}") from exc


def send_message(message: str, model: str = "gpt-5.6-terra", base_url: str = DEFAULT_GATEWAY_URL) -> str:
    """Create a model and send one message."""
    return create_model(model, base_url).invoke(message)
