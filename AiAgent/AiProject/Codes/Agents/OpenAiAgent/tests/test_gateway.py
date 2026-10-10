import json
from unittest.mock import Mock

import httpx

from codex_agent.codex import CodexClient
from codex_agent.openai_gateway import chat_completion


def test_gateway_tool_roundtrip():
    client = Mock()
    client.settings.model = "test-model"
    client.respond.side_effect = [
        {"output": [{"type": "function_call", "call_id": "c1", "name": "weather", "arguments": '{"city":"北京"}'}]},
        "晴天",
    ]
    first = chat_completion({
        "model": "test-model", "messages": [{"role": "user", "content": "北京天气"}],
        "tools": [{"type": "function", "function": {"name": "weather", "parameters": {"type": "object"}}}],
    }, client)
    assert first["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "weather"
    request = [
        {"role": "user", "content": "北京天气"}, first["choices"][0]["message"],
        {"role": "tool", "tool_call_id": "c1", "content": "晴天"},
    ]
    second = chat_completion({"messages": request}, client)
    assert second["choices"][0]["message"]["content"] == "晴天"
    second_input = client.respond.call_args.args[0]
    assert second_input[-2]["name"] == "weather"
    assert second_input[-1] == {"type": "function_call_output", "call_id": "c1", "output": "晴天"}


def test_codex_stream_completion_prefers_final_output():
    final = {"output": [{"type": "function_call", "call_id": "c1", "name": "weather", "arguments": '{"city":"北京"}'}]}
    events = [
        {"type": "response.output_item.added", "output_index": 0, "item": {"id": "i1", "type": "function_call", "call_id": "c1", "name": "weather", "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "output_index": 0, "item_id": "i1", "delta": '{"city":"北京"}'},
        {"type": "response.completed", "response": final},
    ]
    response = httpx.Response(200, headers={"content-type": "text/event-stream"}, text="\n\n".join("data: " + json.dumps(e) for e in events))
    assert CodexClient._decode_structured_response(response) == final
