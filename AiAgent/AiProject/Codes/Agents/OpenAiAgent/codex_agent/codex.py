from __future__ import annotations

import json
from typing import Any, Iterable

import httpx

from .config import Settings
from .oauth import OAuthClient, OAuthError, TokenSet, TokenStore


class CodexError(RuntimeError):
    """Raised when the Codex request fails or cannot be decoded."""


class CodexClient:
    def __init__(self, settings: Settings, oauth: OAuthClient | None = None):
        self.settings = settings
        self.store = TokenStore(settings.token_path)
        self.oauth = oauth or OAuthClient(settings)
        self.http = self.oauth.http

    def ensure_tokens(self) -> TokenSet:
        tokens = self.store.load()
        if tokens is None:
            raise OAuthError("尚未登录，请先执行: codex-agent login")
        if tokens.is_expired():
            tokens = self.oauth.refresh(tokens, self.store)
        return tokens

    def respond(self, messages: list[dict[str, Any]], model: str | None = None) -> str:
        tokens = self.ensure_tokens()
        payload = {
            "model": model or self.settings.model,
            "input": messages,
            "stream": True,
            "store": False,
        }
        response = self.http.post(
            f"{self.settings.codex_base_url}/responses",
            headers=self._headers(tokens),
            json=payload,
        )
        if response.status_code == 401 and tokens.refresh_token:
            tokens = self.oauth.refresh(tokens, self.store)
            response = self.http.post(
                f"{self.settings.codex_base_url}/responses",
                headers=self._headers(tokens),
                json=payload,
            )
        if response.status_code >= 400:
            raise CodexError(f"Codex 请求失败 ({response.status_code}): {response.text}")
        return self._decode_response(response)

    def _headers(self, tokens: TokenSet) -> dict[str, str]:
        headers = {
            "Authorization": f"{tokens.token_type} {tokens.access_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
        }
        if tokens.account_id:
            headers["ChatGPT-Account-ID"] = tokens.account_id
        return headers

    @staticmethod
    def _decode_response(response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "")
        body = response.text
        is_stream = "text/event-stream" in content_type or body.lstrip().startswith(("event:", "data:"))
        if not is_stream:
            try:
                return CodexClient._extract_json(response.json())
            except (ValueError, KeyError, TypeError) as exc:
                raise CodexError(f"无法解析模型响应: {response.text[:500]}") from exc

        chunks: list[str] = []
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
            delta = event.get("delta")
            if isinstance(delta, str):
                chunks.append(delta)
                continue
            # Codex emits response.output_text.delta followed by a
            # response.output_text.done event containing the complete text.
            # The done payload must not be appended again.
            if event.get("type") == "response.output_text.delta" and isinstance(event.get("text"), str):
                chunks.append(event["text"])
                continue
            try:
                extracted = CodexClient._extract_json(event)
            except (KeyError, TypeError):
                continue
            if extracted:
                chunks.append(extracted)
        return "".join(chunks).strip()

    @staticmethod
    def _extract_json(data: dict[str, Any]) -> str:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        output = data.get("output", [])
        texts: list[str] = []
        for item in output if isinstance(output, list) else []:
            content = item.get("content", []) if isinstance(item, dict) else []
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        if texts:
            return "".join(texts)
        if isinstance(data.get("response"), dict):
            return CodexClient._extract_json(data["response"])
        raise KeyError("output_text")


class Conversation:
    def __init__(self, client: CodexClient, system: str | None = None):
        self.client = client
        self.messages: list[dict[str, Any]] = []
        if system:
            self.messages.append({"role": "system", "content": system})

    def ask(self, text: str) -> str:
        self.messages.append({"role": "user", "content": text})
        try:
            answer = self.client.respond(self.messages)
        except Exception:
            self.messages.pop()
            raise
        self.messages.append({"role": "assistant", "content": answer})
        return answer
