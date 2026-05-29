"""Development launcher for the Office bridge."""

from __future__ import annotations

import argparse
import os
import time

from .bridge_auth import OfficeBridgeAuth
from .bridge_server import OfficeBridgeServer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="latexsnipper-office-bridge-dev")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=28765)
    parser.add_argument("--token", default=os.environ.get("LATEXSNIPPER_OFFICE_BRIDGE_TOKEN", "dev-token"))
    args = parser.parse_args(argv)

    server = OfficeBridgeServer(
        host=args.host,
        port=args.port,
        auth=OfficeBridgeAuth(args.token),
    )
    server.start()
    print(f"Office bridge listening on {server.base_url}")
    print(f"Bridge token: {server.token}")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
