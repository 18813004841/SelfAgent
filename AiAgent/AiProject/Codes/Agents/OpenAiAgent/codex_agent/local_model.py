"""LangChain model client for the local LOCALLLMAGENT gateway."""

from __future__ import annotations

import os

from langchain_openai import ChatOpenAI


class ChatLocalLLMAgent(ChatOpenAI):
    """OpenAI-compatible LangChain model backed by the local Codex gateway.

    The API key is only a local gateway key. The gateway itself owns and
    refreshes the real Codex OAuth credentials.
    """

    def __init__(self, *, model: str | None = None, **kwargs):
        kwargs.setdefault("api_key", os.getenv("LOCALLLMAGENT_API_KEY", "local-only"))
        kwargs.setdefault("base_url", os.getenv("LOCALLLMAGENT_API_URL", "http://127.0.0.1:8765/v1"))
        kwargs.setdefault("model", model or os.getenv("LOCALLLMAGENT_MODEL", "gpt-5.6-sol"))
        # The local gateway implements /v1/chat/completions. Newer
        # langchain-openai versions may otherwise auto-select /v1/responses.
        kwargs.setdefault("use_responses_api", False)
        super().__init__(**kwargs)


LOCALLLMAGENT = ChatLocalLLMAgent

__all__ = ["ChatLocalLLMAgent", "LOCALLLMAGENT"]
