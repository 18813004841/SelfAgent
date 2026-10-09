from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    oauth_device_url: str = "https://auth.openai.com/api/accounts/deviceauth/usercode"
    oauth_device_token_url: str = "https://auth.openai.com/api/accounts/deviceauth/token"
    oauth_token_url: str = "https://auth.openai.com/oauth/token"
    codex_base_url: str = "https://chatgpt.com/backend-api/codex"
    client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann"
    model: str = "gpt-5.6-sol"
    timeout_seconds: float = 60.0
    poll_interval_seconds: float = 5.0
    token_path: Path = Path.home() / ".self_agent" / ".codex-agent" / "auth.json"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            oauth_device_url=os.getenv("CODEX_OAUTH_DEVICE_URL", cls.oauth_device_url),
            oauth_device_token_url=os.getenv("CODEX_OAUTH_DEVICE_TOKEN_URL", cls.oauth_device_token_url),
            oauth_token_url=os.getenv("CODEX_OAUTH_TOKEN_URL", cls.oauth_token_url),
            codex_base_url=os.getenv("CODEX_BASE_URL", cls.codex_base_url).rstrip("/"),
            client_id=os.getenv("CODEX_CLIENT_ID", cls.client_id),
            model=os.getenv("CODEX_MODEL", cls.model),
            timeout_seconds=float(os.getenv("CODEX_HTTP_TIMEOUT", cls.timeout_seconds)),
            poll_interval_seconds=float(os.getenv("CODEX_POLL_INTERVAL", cls.poll_interval_seconds)),
            token_path=Path(os.getenv("CODEX_TOKEN_PATH", str(cls.token_path))).expanduser(),
        )
