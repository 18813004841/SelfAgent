from __future__ import annotations

import argparse
import json
import urllib.request


def get(url, token):
    r = urllib.request.Request(url, method="GET")
    r.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server", default="http://127.0.0.1:8765")
    p.add_argument("--token", default="dev-token")
    args = p.parse_args()
    server = args.server.rstrip("/")
    print(json.dumps(get(f"{server}/api/workers", args.token), ensure_ascii=False, indent=2))
    print(json.dumps(get(f"{server}/api/tasks", args.token), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
