"""Installed Office add-in site and TLS configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


OFFICE_ADDIN_PORT = 8765


@dataclass(frozen=True)
class InstalledOfficeAddin:
    root: Path
    site_root: Path
    certificate: Path
    private_key: Path


def find_installed_office_addin() -> InstalledOfficeAddin | None:
    for root in _candidate_roots():
        installed = InstalledOfficeAddin(
            root=root,
            site_root=root / "site",
            certificate=root / "tls" / "server.crt",
            private_key=root / "tls" / "server.key",
        )
        if (
            (installed.site_root / "taskpane.html").is_file()
            and installed.certificate.is_file()
            and installed.private_key.is_file()
        ):
            return installed
    return None


def _candidate_roots() -> list[Path]:
    override = os.environ.get("LATEXSNIPPER_OFFICE_ADDIN_ROOT", "").strip()
    if override:
        return [Path(override).expanduser()]
    if sys.platform == "win32":
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return [Path(program_data) / "LaTeXSnipper" / "OfficeAddin"]
    if sys.platform == "darwin":
        return [
            Path.home() / "Library" / "Application Support" / "LaTeXSnipper" / "OfficeAddin",
            Path("/Library/Application Support/LaTeXSnipper/OfficeAddin"),
        ]
    return []
