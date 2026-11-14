"""LaTeXSnipper Office for Mac: a standalone host for the Word/PowerPoint add-in.

Office for Mac has no VSTO or COM add-ins, so the Windows plugin's editor and
renderer run as an Office web add-in. This package serves its pages over
loopback HTTPS and provides the native services the Windows plugin gets from
.NET. It runs on its own; screenshot recognition is the only feature that
uses the LaTeXSnipper desktop app, through its Automation API.
"""

from __future__ import annotations

from latexsnipper_office.paths import resources_root


def _read_version() -> str:
    try:
        return (resources_root() / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


__version__ = _read_version()
