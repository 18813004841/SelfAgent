from __future__ import annotations

import argparse
import sys

from .codex import CodexClient, Conversation
from .config import Settings
from .oauth import OAuthClient, OAuthError, TokenStore


SYSTEM_PROMPT = "你是一个简洁、可靠的 Codex Agent。先理解用户目标，再给出可执行的回答。"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OAuth-authenticated OpenAI Codex Agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="使用 OAuth 设备码登录")
    logout = sub.add_parser("logout", help="删除本地 OAuth 凭证")
    logout.set_defaults()
    chat = sub.add_parser("chat", help="开始多轮对话")
    chat.add_argument("prompt", nargs="?", help="可选的第一条消息；不提供则进入交互模式")
    chat.add_argument("--model", help="覆盖默认模型")
    return parser

def create_codex_client(model=None):
    settings = Settings.from_env()
    if model:
        settings = Settings(
                oauth_device_url=settings.oauth_device_url,
                oauth_device_token_url=settings.oauth_device_token_url,
                oauth_token_url=settings.oauth_token_url,
                codex_base_url=settings.codex_base_url,
                client_id=settings.client_id,
                model=model,
                timeout_seconds=settings.timeout_seconds,
                poll_interval_seconds=settings.poll_interval_seconds,
                token_path=settings.token_path,
            )         
    client = CodexClient(settings)
    conversation = Conversation(client, SYSTEM_PROMPT)
    return conversation

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    store = TokenStore(settings.token_path)
    try:
        if args.command == "login":
            OAuthClient(settings).device_login(store)
            print(f"登录成功，凭证已保存到: {settings.token_path}")
            return 0
        if args.command == "logout":
            store.delete()
            print("已删除本地凭证")
            return 0
        if args.command == "chat":
            client = CodexClient(settings)
            if args.model:
                settings = Settings(
                    oauth_device_url=settings.oauth_device_url,
                    oauth_device_token_url=settings.oauth_device_token_url,
                    oauth_token_url=settings.oauth_token_url,
                    codex_base_url=settings.codex_base_url,
                    client_id=settings.client_id,
                    model=args.model,
                    timeout_seconds=settings.timeout_seconds,
                    poll_interval_seconds=settings.poll_interval_seconds,
                    token_path=settings.token_path,
                )
                client = CodexClient(settings)
            conversation = Conversation(client, SYSTEM_PROMPT)
            if args.prompt:
                print(conversation.ask(args.prompt))
            return interactive_loop(conversation)
    except OAuthError as exc:
        print(f"认证错误: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已退出")
        return 130
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


def interactive_loop(conversation: Conversation) -> int:
    while True:
        try:
            text = input("\n你> ").strip()
        except EOFError:
            print()
            return 0
        if text.lower() in {"/exit", "/quit", "exit", "quit"}:
            return 0
        if not text:
            continue
        try:
            print(f"\nCodex> {conversation.ask(text)}")
        except Exception as exc:
            print(f"\n请求失败: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
