"""Single-turn OpenAI Agent conversation entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from core.Log import AppLogger

logger = AppLogger("openai-agent.chat-script", "openai_agent")


def ask_once(project_root: Path, message: str, model: str = "gpt-5.6-terra") -> str:
    logger.info("ask_once.begin model=%s message_length=%d project_root=%s", model, len(message), project_root)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from openai_utils import create_model
    try:
        result = create_model(model).invoke(message)
        logger.info("ask_once.end model=%s response_length=%d", model, len(result))
        return result
    except Exception:
        logger.exception("ask_once.error model=%s", model)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("message")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--model", default="gpt-5.6-terra")
    args = parser.parse_args()
    logger.info("main.begin model=%s message_length=%d", args.model, len(args.message))
    try:
        print(ask_once(args.project_root.resolve(), args.message, args.model))
    except Exception as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
