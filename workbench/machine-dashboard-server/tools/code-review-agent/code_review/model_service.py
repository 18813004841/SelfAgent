from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import logging
from pathlib import Path
from typing import Any


class ModelServiceError(RuntimeError): pass

SHARED_POOL_URL = "http://10.0.27.224:8317/v1"
SHARED_POOL_CONFIG = Path(__file__).resolve().parents[3] / "workbench" / "machine-dashboard-server" / "launchers" / "openai_agent" / "shared_pool.local.json"

logger = logging.getLogger("code-review.model-service")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [feature=code-review.model-service] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False


def resolve_api_key(explicit: str | None = None) -> str:
    key = (explicit or os.getenv("SHARED_POOL_API_KEY") or "").strip()
    if not key and SHARED_POOL_CONFIG.is_file():
        data = json.loads(SHARED_POOL_CONFIG.read_text(encoding="utf-8"))
        key = str(data.get("api_key") or "").strip()
    if not key:
        raise ModelServiceError(f"未配置共享池 API Key：{SHARED_POOL_CONFIG} 或环境变量 SHARED_POOL_API_KEY")
    return key


class LocalModelClient:
    def __init__(self, api_url: str = SHARED_POOL_URL, model: str = "gpt-5.6-sol", timeout: float = 120, max_output_tokens: int = 2000, api_key: str | None = None) -> None:
        self.api_url, self.model, self.timeout, self.max_output_tokens = api_url.rstrip("/"), model, timeout, max_output_tokens
        self.api_key = resolve_api_key(api_key)

    def _post(self, payload: dict[str, Any]) -> tuple[int, str]:
        request = urllib.request.Request(
            f"{self.api_url}/responses",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json", "Accept": "text/event-stream, application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelServiceError(str(exc)) from exc

    def complete(self, messages: list[dict[str, str]], stream: bool = False) -> str:
        logger.info("model.request model=%s url=%s stream=%s messages=%d", self.model, self.api_url, stream, len(messages))
        payload = {"model": self.model, "input": messages, "stream": stream, "store": False, "max_output_tokens": self.max_output_tokens}
        status, body = self._post(payload)
        if status == 400 and "Stream must be set to true" in body:
            payload["stream"] = True
            status, body = self._post(payload)
        if status >= 400:
            raise ModelServiceError(f"共享池请求失败 ({status}): {body[:500]}")
        result = _extract_text(body)
        logger.info("model.response model=%s content_length=%d", self.model, len(result))
        return result


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
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "response.output_text.delta" and isinstance(event.get("delta"), str):
                parts.append(event["delta"])
            elif event.get("type") == "response.output_text.done" and isinstance(event.get("text"), str):
                return event["text"]
        if parts:
            return "".join(parts)
        raise ModelServiceError(f"共享池流式响应没有文本: {body[:500]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ModelServiceError("invalid JSON response") from exc
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    texts = [str(part["text"]) for item in data.get("output") or [] for part in item.get("content") or [] if isinstance(part, dict) and part.get("text")]
    if texts:
        return "".join(texts)
    raise ModelServiceError(f"共享池返回格式无效: {body[:500]}")
