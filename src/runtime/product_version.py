from __future__ import annotations

from pathlib import Path
import re
import sys


_PRODUCT_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _version_file() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        return bundle_root / "VERSION"
    return Path(__file__).resolve().parents[2] / "VERSION"


def read_product_version() -> str:
    path = _version_file()
    try:
        version = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Product version file is unavailable: {path}") from exc
    if not _PRODUCT_VERSION_PATTERN.fullmatch(version):
        raise RuntimeError(f"Invalid product version in {path}: {version!r}")
    return version


def product_version_numbers(version: str) -> tuple[int, int, int, int]:
    match = _PRODUCT_VERSION_PATTERN.fullmatch(version)
    if not match:
        raise ValueError(f"Invalid product version: {version!r}")
    return *(int(part) for part in match.groups()), 0


def write_windows_version_info(path: Path, version: str) -> None:
    numbers = product_version_numbers(version)
    dotted = ".".join(str(part) for part in numbers)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '080404B0',
          [
            StringStruct('CompanyName', 'Mathcraft'),
            StringStruct('FileDescription', 'LaTeXSnipper'),
            StringStruct('FileVersion', '{dotted}'),
            StringStruct('InternalName', 'LaTeXSnipper'),
            StringStruct('OriginalFilename', 'LaTeXSnipper.exe'),
            StringStruct('ProductName', 'LaTeXSnipper'),
            StringStruct('ProductVersion', '{dotted}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


PRODUCT_VERSION = read_product_version()
