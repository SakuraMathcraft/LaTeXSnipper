# coding: utf-8

from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_pandoc_optional_dependency_uses_pypandoc() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    specs = data["project"]["optional-dependencies"]["pandoc"]

    assert any(spec.startswith("pypandoc") for spec in specs)
    assert not any(spec.startswith("pandoc") for spec in specs)


def test_build_requirements_use_pypandoc_wrapper() -> None:
    lines = (ROOT / "requirements-build.txt").read_text(encoding="utf-8").splitlines()
    specs = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    assert any(spec.startswith("pypandoc") for spec in specs)
    assert not any(spec.startswith("pandoc") for spec in specs)
