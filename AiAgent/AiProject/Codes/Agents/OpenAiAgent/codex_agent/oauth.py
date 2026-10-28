from __future__ import annotations

import json
import os
import stat
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import Settings
from .log import get_logger


logger = get_logger()


class OAuthError(RuntimeError):
    """Raised when OAuth login or refresh cannot complete."""


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str | None = None
    expires_at: float | None = None
    token_type: str = "Bearer"
    account_id: str | None = None
    id_token: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any], previous: "TokenSet | None" = None) -> "TokenSet":
        expires_in = payload.get("expires_in")
        expires_at = payload.get("expires_at")
        if expires_at is None and expires_in is not None:
            expires_at = time.time() + float(expires_in)
        return cls(
            access_token=payload.get("access_token", previous.access_token if previous else ""),
            refresh_token=payload.get("refresh_token", previous.refresh_token if previous else None),
            expires_at=float(expires_at) if expires_at is not None else None,
            token_type=payload.get("token_type", previous.token_type if previous else "Bearer"),
            account_id=payload.get("account_id", previous.account_id if previous else None),
            id_token=payload.get("id_token", previous.id_token if previous else None),
        )

    def is_expired(self, leeway: float = 60.0) -> bool:
        # Tokens without an expiry are refreshed on every request only if the
        # server supplied no expiry. The official response normally includes one.
        return not self.expires_at or time.time() >= self.expires_at - leeway


class TokenStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> TokenSet | None:
        if not self.path.exists():
            logger.info("OAuth 凭证文件不存在: %s", self.path)
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return TokenSet.from_payload(data)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            logger.exception("读取 OAuth 凭证失败: %s", self.path)
            raise OAuthError(f"无法读取令牌文件 {self.path}: {exc}") from exc

    def save(self, tokens: TokenSet) -> None:
        logger.info("保存 OAuth 凭证: %s", self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(asdict(tokens), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.path)
        if os.name != "nt":
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def delete(self) -> None:
        logger.info("删除 OAuth 凭证: %s", self.path)
        self.path.unlink(missing_ok=True)


class OAuthClient:
    def __init__(self, settings: Settings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=settings.timeout_seconds)

    def device_login(self, store: TokenStore) -> TokenSet:
        logger.info("开始 OAuth 设备登录")
        # OpenAI's current Codex device flow first creates a device_auth_id.
        response = self.http.post(
            self.settings.oauth_device_url,
            json={"client_id": self.settings.client_id},
        )
        self._raise(response, "申请设备码")
        data = response.json()
        device_auth_id = data.get("device_auth_id")
        user_code = data.get("user_code") or data.get("usercode")
        if not device_auth_id or not user_code:
            raise OAuthError(f"设备码响应缺少必要字段: {data}")

        verification_uri = data.get("verification_uri") or "https://auth.openai.com/codex/device"
        print(f"请打开: {verification_uri}")
        print(f"请输入一次性代码: {user_code}")
        expires_at = time.time() + 900
        interval = float(data.get("interval", self.settings.poll_interval_seconds))

        while time.time() < expires_at:
            time.sleep(interval)
            token_response = self.http.post(
                self.settings.oauth_device_token_url,
                json={"device_auth_id": device_auth_id, "user_code": user_code},
            )
            if token_response.status_code < 400:
                device_result = token_response.json()
                authorization_code = device_result.get("authorization_code")
                code_verifier = device_result.get("code_verifier")
                if not authorization_code or not code_verifier:
                    raise OAuthError(f"设备码响应缺少授权码或 PKCE 参数: {device_result}")
                exchange = self.http.post(
                    self.settings.oauth_token_url,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": self.settings.client_id,
                        "code": authorization_code,
                        "redirect_uri": "https://auth.openai.com/deviceauth/callback",
                        "code_verifier": code_verifier,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                self._raise(exchange, "授权码换取令牌")
                tokens = TokenSet.from_payload(exchange.json())
                if not tokens.access_token:
                    raise OAuthError("令牌响应没有 access_token")
                store.save(tokens)
                logger.info("OAuth 设备登录成功")
                return tokens
            if token_response.status_code in {403, 404}:
                continue
            raise OAuthError(f"设备码轮询失败 ({token_response.status_code}): {token_response.text}")
        raise OAuthError("设备码已过期，请重新执行 login")

    def refresh(self, tokens: TokenSet, store: TokenStore) -> TokenSet:
        logger.info("开始刷新 OAuth 凭证")
        if not tokens.refresh_token:
            raise OAuthError("没有 refresh_token，请重新登录")
        response = self.http.post(
            self.settings.oauth_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens.refresh_token,
                "client_id": self.settings.client_id,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._raise(response, "刷新令牌")
        refreshed = TokenSet.from_payload(response.json(), previous=tokens)
        if not refreshed.access_token:
            raise OAuthError("刷新响应没有 access_token")
        store.save(refreshed)
        logger.info("OAuth 凭证刷新成功")
        return refreshed

    @staticmethod
    def _raise(response: httpx.Response, action: str) -> None:
        if response.status_code >= 400:
            logger.error("%s失败: status=%s, body=%s", action, response.status_code, response.text[:500])
            raise OAuthError(f"{action}失败 ({response.status_code}): {response.text}")
