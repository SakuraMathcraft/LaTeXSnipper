from __future__ import annotations

from pathlib import Path
import tomllib

from runtime.distribution import APP_VERSION
from runtime.product_version import (
    PRODUCT_VERSION,
    product_version_numbers,
    write_windows_version_info,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_mathcraft_pypi_version_is_independent_from_product_version() -> None:
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["version"] == "0.2.8"
    assert metadata["project"]["version"] != PRODUCT_VERSION


def test_runtime_product_version_matches_repository_version() -> None:
    version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert PRODUCT_VERSION == version
    assert APP_VERSION == f"v{version}"
    assert product_version_numbers(version) == (
        *(int(part) for part in version.split(".")),
        0,
    )


def test_windows_version_info_uses_product_version(tmp_path: Path) -> None:
    output = tmp_path / "version_info.txt"
    write_windows_version_info(output, PRODUCT_VERSION)
    generated = output.read_text(encoding="utf-8")
    numbers = product_version_numbers(PRODUCT_VERSION)
    dotted = ".".join(str(part) for part in numbers)

    assert f"filevers={numbers}" in generated
    assert f"prodvers={numbers}" in generated
    assert f"StringStruct('FileVersion', '{dotted}')" in generated
    assert f"StringStruct('ProductVersion', '{dotted}')" in generated
