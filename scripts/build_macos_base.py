"""Assemble and sign the reusable macOS base once for each resource identity."""

from __future__ import annotations

import plistlib
import shutil
from pathlib import Path

from release_installers import run

ROOT = Path(__file__).resolve().parents[1]


def sign_macos_tree(directory: Path) -> None:
    magic = {
        b"\xcf\xfa\xed\xfe",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xfe\xed\xfa\xce",
        b"\xca\xfe\xba\xbe",
        b"\xbe\xba\xfe\xca",
        b"\xca\xfe\xba\xbf",
    }
    for path in sorted(
        directory.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if path.is_symlink():
            continue
        if path.is_file():
            with path.open("rb") as stream:
                executable = stream.read(4) in magic
            if executable:
                run(
                    [
                        "codesign",
                        "--force",
                        "--entitlements",
                        ROOT / "packaging/macos/entitlements.plist",
                        "--sign",
                        "-",
                        path,
                    ]
                )
        elif path.suffix in {".framework", ".app"}:
            run(["codesign", "--force", "--sign", "-", path])


def build_macos_base(
    payload: Path, runtime: Path, inference: Path, models: Path
) -> None:
    """Cache the signed nested base as one artifact; daily builds never re-sign weights."""
    from distribution_inputs import (
        load_dependencies,
        load_sources,
        macos_minimum_version,
    )

    sources = load_sources(ROOT / "packaging/runtime/sources.lock.json")
    dependencies = load_dependencies(
        ROOT / "packaging/runtime/dependencies.lock.json", sources
    )
    minimum = macos_minimum_version(sources, dependencies)
    bundle = payload / "LaTeXSnipperBase.bundle"
    resources = bundle / "Contents/Resources"
    resources.mkdir(parents=True)
    for name, source in (
        ("runtime", runtime),
        ("inference", inference),
        ("models", models),
    ):
        shutil.copytree(source, resources / name, symlinks=True)
    (bundle / "Contents/MacOS").mkdir()
    run(
        [
            "clang",
            f"-mmacosx-version-min={minimum}",
            "-O2",
            ROOT / "packaging/macos/launcher.c",
            "-o",
            bundle / "Contents/MacOS/base",
        ]
    )
    with (bundle / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump(
            {
                "CFBundleIdentifier": "com.mathcraft.latexsnipper.base",
                "CFBundlePackageType": "BNDL",
                "CFBundleExecutable": "base",
                "CFBundleVersion": "1",
            },
            stream,
        )
    run(["codesign", "--force", "--sign", "-", bundle / "Contents/MacOS/base"])
    run(["codesign", "--force", "--sign", "-", bundle])
