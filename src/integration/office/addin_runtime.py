"""Installed Office add-in site and TLS configuration."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys


OFFICE_ADDIN_PORT = 8765
WINDOWS_OFFICE_ADDIN_REGISTRY_KEY = r"Software\LaTeXSnipper\OfficeAddin"
WINDOWS_OFFICE_ADDIN_INSTALL_ROOT_VALUE = "InstallRoot"


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
        installed_root = _windows_installed_root()
        return [installed_root] if installed_root is not None else []
    if sys.platform == "darwin":
        return [
            Path.home() / "Library" / "Application Support" / "LaTeXSnipper" / "OfficeAddin",
            Path("/Library/Application Support/LaTeXSnipper/OfficeAddin"),
        ]
    return []


def _windows_installed_root() -> Path | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_OFFICE_ADDIN_REGISTRY_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, WINDOWS_OFFICE_ADDIN_INSTALL_ROOT_VALUE)
    except OSError:
        return None
    root = str(value).strip()
    return Path(root) if root else None
