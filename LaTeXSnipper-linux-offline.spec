# -*- mode: python ; coding: utf-8 -*-
"""Offline PyInstaller spec for Linux: bundle MathCraft model weights with the app."""

import os
from pathlib import Path

os.environ["LATEXSNIPPER_BUNDLE_MATHCRAFT_MODELS"] = "1"
os.environ.setdefault("LATEXSNIPPER_BUILD_NAME", "LaTeXSnipperOffline")

spec_path = Path(SPECPATH) / "LaTeXSnipper-linux.spec"
exec(compile(spec_path.read_text(encoding="utf-8-sig"), str(spec_path), "exec"))
