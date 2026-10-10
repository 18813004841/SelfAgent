"""Loopback-only OpenAI Chat Completions gateway for CodexClient.

Run with ``python -m codex_agent.openai_gateway``. The client-side API key is
only a placeholder; Codex OAuth credentials stay in TokenStore on this host.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

try:
    from .codex import CodexClient, CodexError
    from .config import Settings
    from .log import get_logger
except ImportError:  # support: python path/to/openai_gateway.py
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from codex_agent.codex import CodexClient, CodexError
    from codex_agent.config import Settings
    from codex_agent.log import get_logger

logger = get_logger()


def _to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role == "assistant" and message.get("tool_calls"):
            if content:
                result.append({"role": "assistant", "content": content})
            for call in message["tool_calls"]:
                function = call.get("function") or {}
                result.append({
                    "type": "function_call", "call_id": call["id"],
                    "name": function["name"], "arguments": function.get("arguments") or "{}",
                })
        elif role == "tool":
            result.append({
                "type": "function_call_output", "call_id": message["tool_call_id"],
                "output": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
            })
        elif role in {"system", "developer", "user", "assistant"}:
            if not isinstance(content, str):
                raise ValueError("Only text message content is supported")
            result.append({"role": role, "content": content})
        else:
            raise ValueError(f"Unsupported role: {role}")
    return result


def _to_responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for tool in tools:
        if tool.get("type") != "function":
            raise ValueError("Only function tools are supported")
        function = tool.get("function") or tool
        result.append({
            "type": "function", "name": function["name"],
            "description": function.get("description", ""),
            "parameters": function.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def chat_completion(request: dict[str, Any], client: CodexClient) -> dict[str, Any]:
    """Translate a Chat Completions request/response without executing tools."""
    logger.info("收到网关聊天请求: model=%s, messages=%d, tools=%d", request.get("model"), len(request.get("messages") or []), len(request.get("tools") or []))
    messages = request.get("messages")
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    logger.info("网关收到的消息内容: %s", json.dumps(messages, ensure_ascii=False))
    tools = _to_responses_tools(request.get("tools") or [])
    result = client.respond(
        _to_responses_input(messages), model=request.get("model"), tools=tools or None,
    )
    logger.info("网关模型调用完成")
    text = result if isinstance(result, str) else ""
    calls: list[dict[str, Any]] = []
    if isinstance(result, dict):
        for item in result.get("output", []):
            if item.get("type") == "function_call":
                calls.append({
                    "id": item.get("call_id") or item.get("id"), "type": "function",
                    "function": {"name": item["name"], "arguments": item.get("arguments") or "{}"},
                })
            elif item.get("type") == "message":
                text += "".join(part.get("text", "") for part in item.get("content", []))
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if calls:
        message["tool_calls"] = calls
    logger.info("网关返还给用户的内容: %s", json.dumps(message, ensure_ascii=False))
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}", "object": "chat.completion",
        "created": int(time.time()), "model": request.get("model") or client.settings.model,
        "choices": [{"index": 0, "message": message,
                     "finish_reason": "tool_calls" if calls else "stop"}],
    }


class _Handler(BaseHTTPRequestHandler):
    client: CodexClient

    def _json(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, data: dict[str, Any]) -> None:
        body = f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._json(404, {"error": {"message": "Unknown endpoint"}})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 1_000_000:
                raise ValueError("Invalid request size")
            request = json.loads(self.rfile.read(size))
            result = chat_completion(request, self.client)
        except (ValueError, KeyError, TypeError, CodexError) as exc:
            logger.exception("网关请求处理失败")
            self._json(400, {"error": {"message": str(exc), "type": "invalid_request_error"}})
            return
        if not request.get("stream"):
            self._json(200, result)
            return

        # The upstream Codex call is buffered, but expose a valid Chat
        # Completions SSE sequence so LangChain's stream/astream parsers work.
        choice = result["choices"][0]
        message = choice["message"]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        chunk_base = {"id": result["id"], "object": "chat.completion.chunk",
                      "created": result["created"], "model": result["model"]}
        self._sse({**chunk_base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
        if message.get("content") is not None:
            self._sse({**chunk_base, "choices": [{"index": 0, "delta": {"content": message["content"]}, "finish_reason": None}]})
        for index, call in enumerate(message.get("tool_calls", [])):
            self._sse({**chunk_base, "choices": [{"index": 0, "delta": {"tool_calls": [{
                "index": index, "id": call["id"], "type": "function", "function": call["function"]
            }]}, "finish_reason": None}]})
        self._sse({**chunk_base, "choices": [{"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}]})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main() -> None:
    settings = Settings.from_env()
    _Handler.client = CodexClient(settings)
    port = int(os.getenv("CODEX_GATEWAY_PORT", "8765"))
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    print(f"Codex gateway listening on http://127.0.0.1:{port}/v1", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
