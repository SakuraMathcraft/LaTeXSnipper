"""Locate installation-owned Pandoc or the developer's PATH executable."""

from pathlib import Path
import shutil

from runtime.installed_resources import installed_resources


def resolve_pandoc() -> Path | None:
    resources = installed_resources()
    if resources is not None:
        name = 'pandoc.exe' if resources.manifest.platform == 'windows' else 'pandoc'
        return resources.resource('application', f'pandoc/{name}')
    found = shutil.which('pandoc')
    return Path(found) if found else None
