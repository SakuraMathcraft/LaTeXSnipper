"""Stable desktop entry point that recovers deployment before importing the UI."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    project = Path(__file__).resolve().parents[1]
    sys.path[:0] = [str(project), str(project / "src")]

from runtime.runtime_logging import init_app_logging
from update.deployment_launch import launch_installed

logger = logging.getLogger(f"latexsnipper.{__name__}")


def main() -> int:
    init_app_logging()
    try:
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--installation-root", type=Path)
        arguments, remaining = parser.parse_known_args()
        sys.argv[1:] = remaining
        root = arguments.installation_root or Path(sys.executable).resolve().parent
        launch_installed(root.resolve(strict=True))
        return 0
    except Exception:
        logger.exception("发行启动或恢复失败")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
