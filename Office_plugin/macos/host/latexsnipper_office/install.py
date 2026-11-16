"""Per-user installation of the add-in host.

Installing trusts the loopback certificate (macOS asks the user once) and
registers a LaunchAgent so the host serves Word and PowerPoint from login,
independently of the LaTeXSnipper desktop app. Uninstalling stops the agent
and removes everything this add-in created: the LaunchAgent, its manifests,
the certificate trust and its state directory.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

from latexsnipper_office import certificate, sideload
from latexsnipper_office.lifecycle import prepare_certificate
from latexsnipper_office.paths import (
    BUNDLE_ID,
    ensure_private_directory,
    state_directory,
)

AGENT_LABEL = BUNDLE_ID + ".host"
LAUNCHCTL = "/bin/launchctl"


def agent_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library/LaunchAgents" / f"{AGENT_LABEL}.plist"


def host_command() -> list[str]:
    """How launchd starts this host: the app executable, or the source module."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--serve"]
    return [sys.executable, "-m", "latexsnipper_office", "--serve"]


def agent_definition(command: list[str], logs: Path) -> dict:
    environment = {}
    if not getattr(sys, "frozen", False):
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    definition = {
        "Label": AGENT_LABEL,
        "ProgramArguments": command,
        "RunAtLoad": True,
        # Restart after crashes, but not after a deliberate clean exit.
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Interactive",
        "StandardOutPath": str(logs / "host.log"),
        "StandardErrorPath": str(logs / "host.log"),
        "LimitLoadToSessionType": "Aqua",
    }
    if environment:
        definition["EnvironmentVariables"] = environment
    return definition


def _launchctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [LAUNCHCTL, *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _domain() -> str:
    return f"gui/{os.getuid()}"


def is_installed(home: Path | None = None) -> bool:
    return agent_path(home).is_file()


def is_running() -> bool:
    return (
        _launchctl("print", f"{_domain()}/{AGENT_LABEL}", check=False).returncode == 0
    )


def install(*, state: Path | None = None, home: Path | None = None) -> None:
    state = ensure_private_directory(state or state_directory())
    prepare_certificate(state, interactive=True)
    plist = agent_path(home)
    plist.parent.mkdir(parents=True, exist_ok=True)
    stop_agent(home)
    with plist.open("wb") as stream:
        plistlib.dump(agent_definition(host_command(), state), stream)
    _launchctl("bootstrap", _domain(), str(plist))


def stop_agent(home: Path | None = None) -> None:
    if is_running():
        _launchctl("bootout", f"{_domain()}/{AGENT_LABEL}", check=False)


def uninstall(*, state: Path | None = None, home: Path | None = None) -> None:
    state = state or state_directory()
    stop_agent(home)
    agent_path(home).unlink(missing_ok=True)
    sideload.remove_manifest(home=home)
    certificate.untrust(certificate.certificate_paths(state))
    shutil.rmtree(state, ignore_errors=True)
