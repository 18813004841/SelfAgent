from __future__ import annotations

import argparse
import socket
import sys

PREFIXES = ("10.0.27.", "10.7.71.", "10.0.76.")
CENTRAL_HOST = "10.0.76.228"
CENTRAL_PORT = 18765


def collect_ips() -> list[str]:
    ips: list[str] = []
    try:
        hostname = socket.gethostname()
        for item in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = item[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    # UDP connect does not send packets; it lets OS choose the source LAN IP
    # that would be used to reach the central server.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect((CENTRAL_HOST, CENTRAL_PORT))
        ip = probe.getsockname()[0]
        probe.close()
        if not ip.startswith("127.") and ip not in ips:
            ips.insert(0, ip)
    except Exception:
        pass
    return ips


def detect_machine_id() -> str:
    hostname = socket.gethostname()
    ips = collect_ips()
    for ip in ips:
        if ip.startswith(PREFIXES):
            return "win-pack-" + ip.split(".")[-1]
    return "win-pack-" + hostname


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    machine_id = detect_machine_id()
    if args.debug:
        print(f"hostname={socket.gethostname()}")
        print(f"ips={','.join(collect_ips()) or '-'}")
        print(f"machine_id={machine_id}")
    else:
        print(machine_id)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"detect_machine_id_error={e!r}", file=sys.stderr)
        print("win-pack-" + socket.gethostname())
