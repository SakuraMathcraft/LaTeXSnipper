"""Install the add-in manifest into Word and PowerPoint for Mac.

Office for Mac loads every manifest found in the host's sandboxed ``wef``
directory. The directory belongs to Office, so only the file named after this
add-in is ever written or removed.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path
from xml.sax.saxutils import escape

MANIFEST_FILENAME = "latexsnipper-office-addin.xml"
OFFICE_HOSTS = {
    "word": "com.microsoft.Word",
    "powerpoint": "com.microsoft.Powerpoint",
}


def wef_directory(bundle_id: str, home: Path | None = None) -> Path:
    return (
        (home or Path.home()) / "Library/Containers" / bundle_id / "Data/Documents/wef"
    )


def manifest_version(product_version: str) -> str:
    parts = [part for part in product_version.strip().split(".") if part]
    if not parts or len(parts) > 4 or not all(part.isdigit() for part in parts):
        raise ValueError(f"无效的产品版本：{product_version}")
    return ".".join((parts + ["0", "0", "0"])[:4])


_ICON_URL = re.compile(r"\{\{BASE_URL\}\}/addin/icons/([\w.-]+\.png)")


def render_manifest(
    template: str, *, base_url: str, product_version: str, icons: Path
) -> str:
    """Fill in the template. Icon URLs carry a hash of the icon file:
    Office for Mac caches ribbon icons by URL, so a changed icon needs a new URL.
    """

    if "{{BASE_URL}}" not in template or "{{VERSION}}" not in template:
        raise ValueError("Office 加载项清单模板无效。")

    def versioned(match: re.Match[str]) -> str:
        digest = hashlib.sha256((icons / match.group(1)).read_bytes()).hexdigest()
        return f"{match.group(0)}?v={digest[:12]}"

    return (
        _ICON_URL.sub(versioned, template)
        .replace("{{BASE_URL}}", escape(base_url))
        .replace("{{VERSION}}", manifest_version(product_version))
    )


def installed_hosts(home: Path | None = None) -> list[str]:
    return [
        host
        for host, bundle in OFFICE_HOSTS.items()
        if (wef_directory(bundle, home) / MANIFEST_FILENAME).is_file()
    ]


def available_hosts(home: Path | None = None) -> list[str]:
    """Office apps that have created their sandbox container at least once."""

    root = (home or Path.home()) / "Library/Containers"
    return [host for host, bundle in OFFICE_HOSTS.items() if (root / bundle).is_dir()]


def install_manifest(
    manifest: str, hosts: Iterable[str] | None = None, home: Path | None = None
) -> list[Path]:
    written: list[Path] = []
    for host in hosts or OFFICE_HOSTS:
        directory = wef_directory(OFFICE_HOSTS[host], home)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / MANIFEST_FILENAME
        descriptor, temporary = tempfile.mkstemp(prefix=".latexsnipper-", dir=directory)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(manifest)
            os.replace(temporary, target)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        written.append(target)
    return written


def remove_manifest(home: Path | None = None) -> list[Path]:
    removed: list[Path] = []
    for bundle in OFFICE_HOSTS.values():
        target = wef_directory(bundle, home) / MANIFEST_FILENAME
        if target.is_file():
            target.unlink()
            removed.append(target)
    return removed
