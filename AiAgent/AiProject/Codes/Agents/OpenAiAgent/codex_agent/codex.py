from __future__ import annotations

import json
from typing import Any, Iterable

import httpx

from .config import Settings
from .oauth import OAuthClient, OAuthError, TokenSet, TokenStore
from .log import get_logger


logger = get_logger()


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
            logger.error("未找到 OAuth 凭证: %s", self.settings.token_path)
            raise OAuthError("尚未登录，请先执行: codex-agent login")
        if tokens.is_expired():
            logger.info("OAuth 凭证已过期，开始刷新")
            tokens = self.oauth.refresh(tokens, self.store)
        return tokens

    def respond(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str | dict[str, Any]:
        logger.info("准备发送模型请求: model=%s, messages=%d, tools=%d", model or self.settings.model, len(messages), len(tools or []))
        tokens = self.ensure_tokens()
        payload = {
            "model": model or self.settings.model,
            "input": messages,
            # The Codex endpoint requires streaming even when tools are used.
            "stream": True,
            "store": False,
        }
        if tools:
            payload["tools"] = tools
        logger.info("实际发送给模型的请求: %s", _log_value(payload))
        response = self.http.post(
            f"{self.settings.codex_base_url}/responses",
            headers=self._headers(tokens),
            json=payload,
        )
        logger.info("收到模型 HTTP 响应: status=%s", response.status_code)
        if response.status_code == 401 and tokens.refresh_token:
            logger.warning("模型请求返回 401，刷新凭证后重试")
            tokens = self.oauth.refresh(tokens, self.store)
            response = self.http.post(
                f"{self.settings.codex_base_url}/responses",
                headers=self._headers(tokens),
                json=payload,
            )
        if response.status_code >= 400:
            logger.error("模型请求失败: status=%s, body=%s", response.status_code, response.text[:500])
            raise CodexError(f"Codex 请求失败 ({response.status_code}): {response.text}")
        if tools:
            result = self._decode_structured_response(response)
        else:
            result = self._decode_response(response)
        logger.info("模型响应解析完成: result_type=%s", type(result).__name__)
        logger.info("模型返回内容: %s", _log_value(result))
        return result

    @staticmethod
    def _decode_structured_response(response: httpx.Response) -> dict[str, Any]:
        """Collect streamed Responses API events for tool calling."""
        body = response.text
        is_stream = (
            "text/event-stream" in response.headers.get("content-type", "")
            or body.lstrip().startswith(("data:", "event:"))
        )
        if not is_stream:
            try:
                data = response.json()
            except ValueError as exc:
                raise CodexError("无法解析模型 JSON 响应") from exc
            if isinstance(data, dict) and isinstance(data.get("output"), list):
                return data
            raise CodexError("模型响应缺少 output")
        calls: dict[str, dict[str, Any]] = {}
        text: list[str] = []
        completed_output: list[dict[str, Any]] | None = None
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
            event_type = event.get("type", "")
            if event_type == "response.output_text.delta":
                if isinstance(event.get("delta"), str):
                    text.append(event["delta"])
            elif event_type == "response.function_call_arguments.delta":
                key = event.get("item_id") or str(event.get("output_index", 0))
                call = calls.setdefault(key, {"type": "function_call", "arguments": ""})
                call["arguments"] += event.get("delta", "")
            elif event_type == "response.function_call_arguments.done":
                key = event.get("item_id") or str(event.get("output_index", 0))
                call = calls.setdefault(key, {"type": "function_call", "arguments": ""})
                if isinstance(event.get("arguments"), str):
                    call["arguments"] = event["arguments"]
            elif event_type == "response.output_item.added":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "function_call":
                    key = item.get("id") or str(event.get("output_index", 0))
                    calls[key] = {**calls.get(key, {}), **item}
            elif event_type == "response.output_item.done":
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") == "function_call":
                    key = item.get("id") or str(event.get("output_index", 0))
                    calls[key] = {**calls.get(key, {}), **item}
            elif event_type == "response.completed":
                completed = event.get("response") or {}
                if isinstance(completed.get("output"), list):
                    completed_output = completed["output"]
        if completed_output is not None:
            return {"output": completed_output}
        output = list(calls.values())
        if text:
            output.append({"type": "message", "content": [{"type": "output_text", "text": "".join(text)}]})
        return {"output": output}

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
                data = response.json()
                result = CodexClient._extract_json(data)
                if not result.strip():
                    logger.error("模型返回空内容: status=%s, body=%s", response.status_code, response.text[:1000])
                return result
            except (ValueError, KeyError, TypeError) as exc:
                logger.error("模型响应解析失败: status=%s, body=%s", response.status_code, response.text[:1000])
                raise CodexError(f"无法解析模型响应: {response.text[:500]}") from exc

        chunks: list[str] = []
        saw_delta = False
        event_types: list[str] = []
        stream_error: str | None = None
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
            event_type = event.get("type", "")
            if event_type:
                event_types.append(event_type)
            error = event.get("error")
            if error:
                stream_error = _format_model_error(error)
            elif event_type in {"error", "response.failed", "response.incomplete"}:
                stream_error = _format_model_error(event)
            if stream_error:
                logger.error("模型流式响应报告错误: type=%s, error=%s", event_type, stream_error)
                raise CodexError(f"模型响应失败: {stream_error}")
            delta = event.get("delta")
            if isinstance(delta, str):
                chunks.append(delta)
                saw_delta = True
                continue
            # Codex emits response.output_text.delta followed by a
            # response.output_text.done event containing the complete text.
            # The done payload must not be appended again.
            if event.get("type") == "response.output_text.delta" and isinstance(event.get("text"), str):
                chunks.append(event["text"])
                saw_delta = True
                continue
            # A streamed response can repeat the complete answer in
            # response.output_text.done/response.completed after the deltas.
            # Once deltas were received, those aggregate events are metadata,
            # not additional text, and must not be appended again.
            if saw_delta:
                continue
            try:
                extracted = CodexClient._extract_json(event)
            except (KeyError, TypeError):
                continue
            if extracted:
                chunks.append(extracted)
        result = "".join(chunks).strip()
        if not result:
            logger.error(
                "模型返回空内容: status=%s, event_types=%s, body=%s",
                response.status_code,
                event_types,
                body[:2000],
            )
            raise CodexError("模型返回空内容")
        return result

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
        logger.info("收到用户消息: %s", text)
        self.messages.append({"role": "user", "content": text})
        try:
            answer = self.client.respond(self.messages)
        except Exception:
            logger.exception("处理用户消息失败")
            self.messages.pop()
            raise
        self.messages.append({"role": "assistant", "content": answer})
        logger.info("准备返还模型内容给用户")
        logger.info("返还给用户的内容: %s", _log_value(answer))
        return answer


def _log_value(value: Any) -> str:
    """Serialize complete message content as readable, single-line JSON."""
    return json.dumps(value, ensure_ascii=False, default=str)


def _format_model_error(error: Any) -> str:
    """Extract a useful, log-safe message from an API error event."""
    if isinstance(error, dict):
        for key in ("message", "detail", "code", "status"):
            value = error.get(key)
            if value:
                return f"{key}={value}"
        return _log_value(error)
    return str(error)
