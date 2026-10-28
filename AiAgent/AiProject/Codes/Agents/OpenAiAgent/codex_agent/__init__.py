"""OAuth-authenticated Codex agent."""

__version__ = "0.1.0"

try:
    from .local_model import ChatLocalLLMAgent, LOCALLLMAGENT
except ImportError:
    # Keep the OAuth CLI usable when the optional LangChain extra is absent.
    ChatLocalLLMAgent = None
    LOCALLLMAGENT = None

__all__ = ["ChatLocalLLMAgent", "LOCALLLMAGENT"]
