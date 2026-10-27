"""Run installed desktop acceptance in a real, isolated KWin Wayland session."""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

logger = logging.getLogger("latexsnipper.wayland_acceptance")


def authorize_shortcuts() -> None:
    pyatspi = importlib.import_module("pyatspi")

    def accept(widget) -> None:
        if widget.getRole() == pyatspi.ROLE_PUSH_BUTTON and widget.name in {
            "Allow",
            "OK",
        }:
            action = widget.queryAction()
            if widget.getState().contains(pyatspi.STATE_ENABLED):
                action.doAction(0)
                print(
                    "Authorized the CI shortcut request through the real portal dialog.",
                    flush=True,
                )
            return
        for child in widget:
            accept(child)

    while True:
        try:
            for application in pyatspi.Registry.getDesktop(0):
                if "portal" in application.name.lower():
                    accept(application)
        except Exception:
            logger.debug("Portal accessibility tree changed", exc_info=True)
        time.sleep(0.2)


def run_session(command: list[str], result: Path) -> None:
    keys = [
        "WAYLAND_DISPLAY",
        "DISPLAY",
        "XDG_RUNTIME_DIR",
        "XDG_SESSION_TYPE",
        "XDG_CURRENT_DESKTOP",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "QT_QPA_PLATFORM",
        "QT_LINUX_ACCESSIBILITY_ALWAYS_ON",
        "QT_QUICK_BACKEND",
    ]
    subprocess.run(
        [
            "dbus-update-activation-environment",
            *(key for key in keys if key in os.environ),
        ],
        check=True,
    )
    subprocess.run(
        [
            "gdbus",
            "call",
            "--session",
            "--dest",
            "org.a11y.Bus",
            "--object-path",
            "/org/a11y/bus",
            "--method",
            "org.a11y.Bus.GetAddress",
        ],
        check=True,
    )
    deadline = time.monotonic() + 30
    while True:
        portal = subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.freedesktop.portal.Desktop",
                "--object-path",
                "/org/freedesktop/portal/desktop",
                "--method",
                "org.freedesktop.DBus.Properties.Get",
                "org.freedesktop.portal.GlobalShortcuts",
                "version",
            ],
            capture_output=True,
            encoding="utf-8",
            timeout=15,
        )
        if portal.returncode == 0:
            print(
                "Real Wayland GlobalShortcuts portal: " + portal.stdout.strip(),
                flush=True,
            )
            break
        if time.monotonic() > deadline:
            raise RuntimeError(
                "Wayland GlobalShortcuts portal unavailable: " + portal.stderr
            )
        time.sleep(1)
    authorization = subprocess.Popen(
        [
            "/usr/bin/python3",
            "-X",
            "utf8",
            str(Path(__file__).resolve()),
            "--authorize",
        ],
    )
    try:
        code = subprocess.run(command).returncode
        result.write_text(json.dumps({"returncode": code}), encoding="utf-8")
        if code:
            raise SystemExit(code)
    finally:
        authorization.terminate()
        authorization.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", action="store_true")
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--result", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("Wayland acceptance requires an isolated GitHub Actions runner")
    if args.authorize:
        authorize_shortcuts()
        return
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("An acceptance command is required")
    if args.session:
        run_session(command, args.result)
        return
    with tempfile.TemporaryDirectory(prefix="wayland-acceptance-") as temporary:
        work = Path(temporary).resolve()
        runtime = work / "runtime"
        runtime.mkdir(mode=0o700)
        portals = work / "config/xdg-desktop-portal"
        portals.mkdir(parents=True)
        (portals / "portals.conf").write_text(
            "[preferred]\ndefault=kde\n", encoding="utf-8"
        )
        session = work / "session.sh"
        result = work / "result.json"
        session.write_text(
            "#!/bin/sh\nexec "
            + shlex.join(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(Path(__file__).resolve()),
                    "--session",
                    "--result",
                    str(result),
                    "--",
                    *command,
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        session.chmod(0o755)
        environment = {
            **os.environ,
            "XDG_RUNTIME_DIR": str(runtime),
            "XDG_CONFIG_HOME": str(work / "config"),
            "XDG_CACHE_HOME": str(work / "cache"),
            "XDG_DATA_HOME": str(work / "data"),
            "XDG_CURRENT_DESKTOP": "KDE",
            "XDG_SESSION_TYPE": "wayland",
            "QT_QPA_PLATFORM": "wayland",
            "QT_QUICK_BACKEND": "software",
            "QT_LINUX_ACCESSIBILITY_ALWAYS_ON": "1",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "LANG": "C.UTF-8",
        }
        subprocess.run(
            [
                "dbus-run-session",
                "--",
                "kwin_wayland",
                "--virtual",
                "--xwayland",
                "--no-lockscreen",
                "--exit-with-session",
                str(session),
            ],
            env=environment,
            check=True,
            timeout=2400,
        )
        outcome = json.loads(result.read_text(encoding="utf-8"))
        if outcome["returncode"]:
            raise SystemExit(outcome["returncode"])


if __name__ == "__main__":
    main()
