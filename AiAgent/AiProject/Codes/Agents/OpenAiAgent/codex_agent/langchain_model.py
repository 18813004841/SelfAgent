"""LangChain adapter for the existing CodexClient.

Install the optional dependency with ``pip install -e '.[langchain]'``.
The underlying client buffers the full response: stream() emits one completed
message rather than live token deltas.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ChatMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from .codex import CodexClient
from .config import Settings


class CodexChatModel(BaseChatModel):
    """Use CodexClient through LangChain's standard chat-model interface.

    Pass an existing client, or omit it to use Settings.from_env(). History is
    supplied by the caller/LangGraph, not duplicated in a Conversation object.
    BaseChatModel supplies async execution via its synchronous fallback.
    """

    client: CodexClient = Field(exclude=True, repr=False)
    model: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)

    def __init__(self, *, client: CodexClient | None = None, **kwargs: Any):
        super().__init__(
            client=client if client is not None else CodexClient(Settings.from_env()),
            **kwargs,
        )

    @property
    def _llm_type(self) -> str:
        return "codex-oauth"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model": self.model or self.client.settings.model}

    @staticmethod
    def _convert_messages(messages: list[BaseMessage]) -> list[dict[str, Any]]:
        roles = {"system": "system", "human": "user", "ai": "assistant"}
        converted = []
        for message in messages:
            # ToolMessage must be converted before generic role validation.
            if isinstance(message, ToolMessage):
                converted.append({
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                })
                continue
            role = message.role if isinstance(message, ChatMessage) else roles.get(message.type)
            if role not in {"system", "user", "assistant", "developer"}:
                raise ValueError(f"Unsupported Codex message role: {message.type}")
            if getattr(message, "tool_calls", None):
                import json
                for call in message.tool_calls:
                    converted.append({
                        "type": "function_call",
                        "call_id": call["id"],
                        "name": call["name"],
                        "arguments": json.dumps(call.get("args", {}), ensure_ascii=False),
                    })
                continue
            if not isinstance(message.content, str):
                raise ValueError("CodexChatModel currently accepts text message content only")
            converted.append({"role": role, "content": message.content})
        return converted

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if kwargs:
            raise TypeError(f"Unsupported Codex request options: {', '.join(sorted(kwargs))}")
        if stop:
            raise NotImplementedError("CodexClient does not support stop sequences")
        result = self.client.respond(
            self._convert_messages(messages), model=self.model, tools=self.tools or None
        )
        if isinstance(result, str):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=result))])
        output = result.get("output", [])
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for item in output if isinstance(output, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "function_call":
                import json
                name = item.get("name", "")
                # Some Codex SSE streams omit name on argument delta/done
                # events. Recover it from the bound schema when unambiguous.
                if not name and len(self.tools) == 1:
                    name = self.tools[0].get("name", "")
                if not name:
                    raise ValueError("Codex function_call response did not contain a tool name")
                raw_args = item.get("arguments", {})
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args) if raw_args.strip() else {}
                    except json.JSONDecodeError:
                        # Some streamed responses may end before the final
                        # arguments event. Keep the agent loop alive and let
                        # the tool receive an empty argument object.
                        args = {}
                else:
                    args = raw_args or {}
                tool_calls.append({
                    "name": name,
                    "args": args,
                    "id": item.get("call_id") or item.get("id"),
                    "type": "tool_call",
                })
            for part in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content="".join(text_parts), tool_calls=tool_calls
        ))])

    def run(self, input: str | list[BaseMessage], **kwargs: Any) -> str:
        """Convenience compatibility method returning plain text.

        ``invoke()`` is LangChain's preferred API. This method is useful for
        simple scripts that previously called ``llm.run("...")``.
        """
        if isinstance(input, str):
            result = self.invoke(input, **kwargs)
        else:
            result = self.invoke(input, **kwargs)
        return result.content if isinstance(result.content, str) else str(result.content)

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        if kwargs:
            raise NotImplementedError(f"Unsupported tool options: {', '.join(kwargs)}")
        response_tools = []
        for tool in tools:
            schema = convert_to_openai_tool(tool)
            # LangChain returns Chat Completions shape:
            # {"type": "function", "function": {"name", "parameters"}}.
            # The Codex Responses endpoint expects the function fields flat.
            function = schema.get("function") if isinstance(schema, dict) else None
            if isinstance(function, dict):
                response_tools.append({"type": "function", **function})
            else:
                response_tools.append(schema)
        return self.model_copy(update={"tools": response_tools})
