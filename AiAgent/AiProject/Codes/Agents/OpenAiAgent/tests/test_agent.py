import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
import codex_agent
import codex_agent.cli


def main():
    conversation = codex_agent.cli.create_codex_client("gpt-5.6-sol")
    try:
        answer = conversation.ask("你好")
    except Exception as exc:
            print(f"错误: {exc}")
            return 1

    print(answer)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
