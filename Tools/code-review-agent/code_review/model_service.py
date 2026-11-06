from __future__ import annotations

import json
import urllib.error
import urllib.request
import logging
from typing import Any, Iterator


class ModelServiceError(RuntimeError): pass

logger = logging.getLogger("code-review.model-service")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [feature=code-review.model-service] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False


class LocalModelClient:
    def __init__(self, api_url: str, model: str, timeout: float = 120, max_output_tokens: int = 2000) -> None:
        self.api_url, self.model, self.timeout, self.max_output_tokens = api_url.rstrip("/"), model, timeout, max_output_tokens

    def _request(self, payload: dict[str, Any]) -> Iterator[bytes]:
        req = urllib.request.Request(f"{self.api_url}/chat/completions", json.dumps(payload, ensure_ascii=False).encode(), {"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                yield from response
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ModelServiceError(str(exc)) from exc

    def complete(self, messages: list[dict[str, str]], stream: bool = False) -> str:
        logger.info("model.request model=%s stream=%s messages=%d", self.model, stream, len(messages))
        payload = {"model": self.model, "messages": messages, "stream": stream, "max_tokens": self.max_output_tokens}
        if not stream:
            try: data = json.loads(b"".join(self._request(payload)).decode())
            except (json.JSONDecodeError, UnicodeDecodeError) as exc: raise ModelServiceError("invalid JSON response") from exc
            try:
                result = str(data["choices"][0]["message"]["content"])
                logger.info("model.response model=%s content_length=%d", self.model, len(result))
                return result
            except (KeyError, IndexError, TypeError) as exc: raise ModelServiceError(f"invalid response: {data!r}") from exc
        chunks: list[str] = []
        for raw in self._request(payload):
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"): continue
            value = line[5:].strip()
            if value == "[DONE]": break
            try: data = json.loads(value)
            except json.JSONDecodeError: continue
            delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta: chunks.append(str(delta))
        result = "".join(chunks)
        logger.info("model.stream.end model=%s content_length=%d", self.model, len(result))
        return result
