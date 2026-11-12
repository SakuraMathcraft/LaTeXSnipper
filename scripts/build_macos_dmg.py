"""Build LaTeXSnipper.app and a DMG on this Mac from the locked build inputs.

The release workflow assembles the same components on macOS runners and parks
each immutable payload in a private draft release so later builds can reuse it.
This script performs the identical steps locally, without that release cache,
without the GitHub upload and without notarisation, so the result is an
ad-hoc signed DMG that is ready to install on this machine.

    python -X utf8 scripts/build_macos_dmg.py

Run it from a virtual environment that has requirements.txt and
requirements-build.txt installed and Python 3.11.4 or newer: the GUI host is
frozen from this interpreter and the inference payload unpacks its own Python
with tarfile's data filter.

Every stage is skipped when its payload already exists in the work directory,
so an interrupted build resumes instead of starting over. Use ``--force`` to
throw the work directory away and build everything again; the download cache
is separate and is always reused.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from argparse import Namespace
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from desktop_distribution import write_json  # noqa: E402
from release_artifacts import artifact  # noqa: E402
from release_installers import run  # noqa: E402
from runtime.distribution_manifest import (  # noqa: E402
    DistributionManifest,
    ManifestError,
)

SOURCES = ROOT / "packaging/runtime/sources.lock.json"
DEPENDENCIES = ROOT / "packaging/runtime/dependencies.lock.json"
RESOURCES = ROOT / "packaging/runtime/resources.lock.json"
RELEASES = "https://github.com/SakuraMathcraft/LaTeXSnipper/releases/download"

EDITION = "cpu"


def product_version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def target() -> str:
    from runtime.installed_resources import current_target

    system, architecture = current_target()
    if system != "macos" or architecture != "arm64":
        raise ManifestError(
            "macOS DMGs are only assembled on Apple Silicon Macs; "
            f"this host is {system}-{architecture}"
        )
    return f"{system}-{architecture}"


def check_interpreter() -> None:
    """The inference payload unpacks its Python with tarfile's data filter."""
    if sys.version_info < (3, 11, 4):
        raise ManifestError(
            "Building the inference payload needs Python 3.11.4 or newer "
            f"(tarfile data filter); this interpreter is {sys.version.split()[0]}"
        )


def ensure_build_tools(install: bool) -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError as error:
        if not install:
            raise ManifestError(
                "PyInstaller is required: python -m pip install -r requirements-build.txt"
            ) from error
        print("Installing the freezing tools from requirements-build.txt", flush=True)
        run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                ROOT / "requirements-build.txt",
            ]
        )


@contextmanager
def stage(name: str):
    started = time.monotonic()
    print(f"\n==> {name}", flush=True)
    try:
        yield
    except BaseException:
        print(f"<== {name} failed after {time.monotonic() - started:.1f}s", flush=True)
        raise
    print(f"<== {name} done in {time.monotonic() - started:.1f}s", flush=True)


def payload(work: Path, name: str) -> Path:
    directory = work / name
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "payload"


def build_runtime(destination: Path, build_target: str) -> None:
    from build_gui_runtime import build_gui_runtime

    build_gui_runtime(destination, build_target)


def build_models(destination: Path, cache: Path) -> None:
    from build_desktop_resources import assemble

    assemble(destination, cache, RESOURCES)


def build_inference(destination: Path, build_target: str, cache: Path) -> None:
    from build_inference_component import assemble

    assemble(
        Namespace(
            target=build_target,
            edition=EDITION,
            output=destination,
            cache=cache,
            catalog=SOURCES,
            dependencies=DEPENDENCIES,
            validate_gpu=False,
        )
    )


def build_maintenance(destination: Path) -> None:
    from build_desktop_release import build_maintenance as freeze_maintenance

    freeze_maintenance(destination)


def build_base(destination: Path, parts: dict[str, Path]) -> None:
    from build_macos_base import build_macos_base

    build_macos_base(destination, parts["runtime"], parts["inference"], parts["models"])


def build_application(
    destination: Path, parts: dict[str, Path], build_target: str
) -> None:
    from build_application_resources import assemble

    assemble(Namespace(application=destination, target=build_target))
    shutil.copytree(
        parts["maintenance"], destination, dirs_exist_ok=True, symlinks=True
    )


def strip_finder_metadata(directory: Path) -> None:
    """Finder writes .DS_Store into every build folder it shows.

    The app bundle links the frozen runtime's entries into Contents/Frameworks,
    and codesign refuses a symlinked .DS_Store, so payloads must not carry one.
    """
    for path in directory.rglob(".DS_Store"):
        if path.is_file() and not path.is_symlink():
            path.unlink()


def sign_payload(directory: Path) -> None:
    """Ad-hoc sign every Mach-O in a payload, as the release build does."""
    from build_macos_base import sign_macos_tree

    stamp = directory.parent / "signed"
    if stamp.exists():
        print(f"Reusing signatures: {directory}", flush=True)
        return
    sign_macos_tree(directory)
    stamp.write_text("signed\n", encoding="utf-8")


def component(name: str, source: Path, build_target: str):
    """Inventory a payload with a placeholder artifact; nothing is uploaded."""
    from mathcraft_ocr.protocol import MODEL_FORMAT, WORKER_PROTOCOL
    from runtime.component_inventory import inventory_component
    from runtime.distribution_manifest import Artifact, Component

    system, architecture = build_target.split("-")
    return Component(
        name,
        system,
        architecture,
        "common",
        0 if name == "models" else WORKER_PROTOCOL,
        MODEL_FORMAT,
        inventory_component(source),
        Artifact(f"{RELEASES}/local/pending.zip", "0" * 64, 1),
    )


def assemble_layout(work: Path, parts: dict[str, Path], manifest) -> Path:
    from release_installers import link_or_copy

    layout = work / "layout"
    layout.mkdir()
    shutil.copytree(
        parts["application"],
        layout / "application",
        symlinks=True,
        copy_function=link_or_copy,
        ignore=shutil.ignore_patterns(".DS_Store"),
    )
    shutil.copytree(
        parts["base"] / "LaTeXSnipperBase.bundle",
        layout / "LaTeXSnipperBase.bundle",
        symlinks=True,
        copy_function=link_or_copy,
        ignore=shutil.ignore_patterns(".DS_Store"),
    )
    # The bootstrap is the recovery entry point; macOS starts the GUI host that
    # lives in the base bundle, so the copy only mirrors the other platforms.
    shutil.copy2(layout / "application/bootstrap/LaTeXSnipper", layout / "LaTeXSnipper")
    write_json(layout / "distribution.json", manifest.installed_identity().to_dict())
    return layout


def package(work: Path, parts: dict[str, Path], output: Path, manifest):
    from build_desktop_release import create_macos_bundle
    from release_installers import macos_installer
    from runtime.installation_layout import macos_bundle

    layout = assemble_layout(work, parts, manifest)
    bundle = create_macos_bundle(layout, manifest)
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", bundle])
    return macos_installer(
        macos_bundle(bundle / "Contents/Resources/desktop"), output, manifest
    )


def build(arguments) -> Path:
    check_interpreter()
    build_target = target()
    version = product_version()
    tag = arguments.tag or f"v{version}"
    work = arguments.work.resolve()
    cache = arguments.cache.resolve()
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if arguments.force and work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    # Packaging products are cheap to derive and block a rerun if left behind.
    for leftover in ("layout", "LaTeXSnipper.app", "dmg", "latexsnipper.iconset"):
        path = work / leftover
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)
    cache.mkdir(parents=True, exist_ok=True)
    print(
        f"Building LaTeXSnipper {version} ({build_target})"
        f"\n  work   {work}\n  cache  {cache}\n  output {output}",
        flush=True,
    )
    ensure_build_tools(install=not arguments.skip_tool_install)
    parts: dict[str, Path] = {}

    def reuse(name: str, builder, *, signed: bool = False) -> Path:
        destination = payload(work, name)
        complete = destination.parent / "complete"
        if complete.exists() and destination.is_dir():
            print(f"Reusing {name} payload: {destination}", flush=True)
        else:
            # Without the stamp the payload is partial: discard it, the old
            # signature stamp and any temporary directories a builder left.
            for entry in destination.parent.iterdir():
                if entry.is_dir() and not entry.is_symlink():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
            with stage(name):
                builder(destination)
            complete.write_text("complete\n", encoding="utf-8")
        strip_finder_metadata(destination)
        if signed:
            sign_payload(destination)
        return destination

    parts["runtime"] = reuse(
        "runtime",
        lambda out: build_runtime(out, build_target),
        signed=True,
    )
    parts["models"] = reuse("models", lambda out: build_models(out, cache))
    parts["inference"] = reuse(
        "inference",
        lambda out: build_inference(out, build_target, cache),
        signed=True,
    )
    parts["maintenance"] = reuse("maintenance", build_maintenance, signed=True)
    parts["base"] = reuse("base", lambda out: build_base(out, parts))
    parts["application"] = reuse(
        "application", lambda out: build_application(out, parts, build_target)
    )
    with stage("manifest"):
        manifest = DistributionManifest(
            version,
            "macos",
            "arm64",
            EDITION,
            component("application", parts["application"], build_target),
            component("base", parts["base"], build_target).content_sha256,
            release_tag=tag,
        )
    with stage("dmg"):
        carrier = package(work, parts, output, manifest)
    manifest = replace(manifest, installer=artifact(carrier, f"{RELEASES}/{tag}"))
    write_json(output / f"distribution-macos-arm64-{EDITION}.json", manifest.to_dict())
    return carrier


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work",
        type=Path,
        default=ROOT / "build/macos-dmg",
        help="intermediate payloads; rebuilt stages are reused",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=ROOT / "build/downloads",
        help="verified download cache shared with the release build",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist/desktop",
        help="directory receiving the DMG and its distribution metadata",
    )
    parser.add_argument(
        "--force", action="store_true", help="discard the work directory first"
    )
    parser.add_argument(
        "--tag",
        default="",
        help="release tag recorded in the manifest (default vVERSION)",
    )
    parser.add_argument(
        "--skip-tool-install",
        action="store_true",
        help="fail instead of installing requirements-build.txt",
    )
    arguments = parser.parse_args()
    try:
        carrier = build(arguments)
    except ManifestError as error:
        raise SystemExit(f"Build stopped: {error}") from error
    print(
        f"\nDMG: {carrier}\n     {carrier.stat().st_size / 2**20:.0f} MiB",
        flush=True,
    )


if __name__ == "__main__":
    main()
