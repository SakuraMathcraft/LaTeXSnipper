"""Build the fixed GUI host from its locked dependencies and assets."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from build_desktop_resources import assemble_pandoc
from distribution_inputs import load_resources
from release_installers import run

ROOT = Path(__file__).resolve().parents[1]


def build_gui_runtime(payload: Path, target: str, cache: Path) -> None:
    system = target.split("-")[0]
    build = payload.parent
    run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            build / "frozen",
            "--workpath",
            build / "pyinstaller",
            ROOT / "LaTeXSnipper.spec",
        ]
    )
    (build / "frozen/LaTeXSnipper").rename(payload)
    lock = load_resources(ROOT / "packaging/runtime/resources.lock.json")
    assemble_pandoc(lock, target, payload / "pandoc", cache)
    shutil.copytree(ROOT / "src/assets/MathJax", payload / "assets/MathJax")
    if system == "windows":
        run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                ROOT / "scripts/normalize_windows_crt.ps1",
                "-DistributionRoot",
                payload,
            ]
        )
    for name in ("frozen", "pyinstaller"):
        shutil.rmtree(build / name)
