"""Build LaTeXSnipper.app and a DMG on this Mac from the locked build inputs.

The release workflow assembles the same components on macOS runners and parks
each immutable payload in a private draft release so later builds can reuse it.
This script performs the identical steps locally, without that release cache,
without the GitHub upload and without notarisation, so the result is an
ad-hoc signed DMG that is ready to install on this machine.

    python -X utf8 scripts/release/build_macos_dmg.py

Run it from a virtual environment that has requirements.txt and
requirements-build.txt installed and Python 3.11.4 or newer: the GUI host is
frozen from this interpreter and the inference payload unpacks its own Python
with tarfile's data filter.

Completed component payloads are reused while their input fingerprints match.
The application and DMG are assembled on each run. Use ``--force`` to rebuild
the cached components; the separate download cache is always reused.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from argparse import Namespace
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from importlib import import_module
from importlib.metadata import distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts/release")]

from desktop_distribution import write_json  # noqa: E402
from release_artifacts import artifact  # noqa: E402
from release_build_inputs import build_inputs, fingerprint  # noqa: E402
from release_installers import run  # noqa: E402
from runtime.distribution_manifest import (  # noqa: E402
    Component,
    DistributionManifest,
    ManifestError,
)

SOURCES = ROOT / "packaging/runtime/sources.lock.json"
DEPENDENCIES = ROOT / "packaging/runtime/dependencies.lock.json"
RESOURCES = ROOT / "packaging/runtime/resources.lock.json"
RELEASES = "https://github.com/SakuraMathcraft/LaTeXSnipper/releases/download"

EDITION = "cpu"
WORKSPACE_LOCK = ".latexsnipper-macos-dmg"
CACHED_STAGES = ("runtime", "models", "inference", "maintenance", "base")


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
        import_module("PyInstaller")
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
def stage(name: str) -> Iterator[None]:
    started = time.monotonic()
    print(f"\n==> {name}", flush=True)
    try:
        yield
    except BaseException:
        print(f"<== {name} failed after {time.monotonic() - started:.1f}s", flush=True)
        raise
    print(f"<== {name} done in {time.monotonic() - started:.1f}s", flush=True)


def prepare_workspace(work: Path, cache: Path, output: Path) -> Path:
    for directory in (cache, output):
        if any(directory.is_relative_to(work / name) for name in CACHED_STAGES):
            raise ManifestError(
                f"Cache and output cannot be inside a build stage: {directory}"
            )
    work.mkdir(parents=True, exist_ok=True)
    lock = work / WORKSPACE_LOCK
    if lock.is_symlink():
        raise ManifestError(f"Workspace marker must be a regular file: {lock}")
    if not lock.is_file():
        if any(work.iterdir()):
            raise ManifestError(f"Choose an empty build workspace: {work}")
        lock.touch(exist_ok=False)
    return lock


@contextmanager
def build_workspace(work: Path, cache: Path, output: Path) -> Iterator[None]:
    import fcntl

    with prepare_workspace(work, cache, output).open("r+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ManifestError(
                f"A build is already using this workspace: {work}"
            ) from error
        yield


def stage_inputs(build_target: str) -> dict[str, str]:
    keys = build_inputs(ROOT, build_target)
    environment = {
        "executable": str(Path(sys.executable).resolve()),
        "python": sys.version,
        "packages": sorted((entry.name, entry.version) for entry in distributions()),
    }
    local_script = [Path(__file__).resolve()]
    for name in ("runtime", "maintenance"):
        keys[name] = fingerprint(ROOT, local_script, [keys[name], environment])
    keys["inference"] = fingerprint(
        ROOT, local_script, [keys[f"inference-{EDITION}"], sys.version]
    )
    keys["models"] = keys.pop(f"models-{EDITION}")
    keys["base"] = fingerprint(
        ROOT,
        local_script,
        [keys[name] for name in ("base", "runtime", "inference", "models")],
    )
    return keys


def build_cached_stage(
    directory: Path,
    key: str,
    builder: Callable[[Path], None],
    *,
    force: bool,
    signed: bool,
) -> bool:
    destination = directory / "payload"
    complete = directory / "complete"
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ManifestError(f"Build stage must be a regular directory: {directory}")
    if (
        not force
        and destination.is_dir()
        and not destination.is_symlink()
        and complete.is_file()
        and not complete.is_symlink()
        and complete.read_bytes() == key.encode("ascii")
    ):
        print(f"Reusing {directory.name} payload: {destination}", flush=True)
        strip_finder_metadata(destination)
        return False
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir()
    with stage(directory.name):
        builder(destination)
        strip_finder_metadata(destination)
        if signed:
            from build_macos_base import sign_macos_tree

            sign_macos_tree(destination)
        complete.write_text(key, encoding="utf-8")
    return True


def build_runtime(destination: Path, build_target: str) -> None:
    from build_gui_runtime import build_gui_runtime

    build_gui_runtime(destination, build_target)


def build_models(destination: Path, cache: Path) -> None:
    from build_desktop_resources import assemble

    assemble(destination, cache, RESOURCES, EDITION)


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


def component(name: str, source: Path, build_target: str) -> Component:
    """Inventory a payload with a placeholder artifact; nothing is uploaded."""
    from mathcraft_ocr.protocol import MODEL_FORMAT, WORKER_PROTOCOL
    from runtime.component_inventory import inventory_component
    from runtime.distribution_manifest import Artifact

    system, architecture = build_target.split("-")
    return Component(
        name,
        system,
        architecture,
        EDITION if name == "models" else "common",
        0 if name == "models" else WORKER_PROTOCOL,
        MODEL_FORMAT,
        inventory_component(source),
        Artifact(f"{RELEASES}/local/pending.zip", "0" * 64, 1),
    )


def assemble_layout(
    work: Path, parts: dict[str, Path], manifest: DistributionManifest
) -> Path:
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


def package(
    work: Path, parts: dict[str, Path], output: Path, manifest: DistributionManifest
) -> Path:
    from build_desktop_release import create_macos_bundle
    from release_installers import macos_installer
    from runtime.installation_layout import macos_bundle

    layout = assemble_layout(work, parts, manifest)
    bundle = create_macos_bundle(layout, manifest)
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", bundle])
    return macos_installer(
        macos_bundle(bundle / "Contents/Resources/desktop"), output, manifest
    )


def build(arguments: Namespace) -> Path:
    check_interpreter()
    build_target = target()
    version = product_version()
    tag = arguments.tag or f"v{version}"
    work = arguments.work.resolve()
    cache = arguments.cache.resolve()
    output = arguments.output.resolve()
    print(
        f"Building LaTeXSnipper {version} ({build_target})"
        f"\n  work   {work}\n  cache  {cache}\n  output {output}",
        flush=True,
    )
    with build_workspace(work, cache, output):
        cache.mkdir(parents=True, exist_ok=True)
        output.mkdir(parents=True, exist_ok=True)
        ensure_build_tools(install=not arguments.skip_tool_install)
        keys = stage_inputs(build_target)
        parts = {name: work / name / "payload" for name in CACHED_STAGES}
        builders: dict[str, Callable[[Path], None]] = {
            "runtime": lambda out: build_runtime(out, build_target),
            "models": lambda out: build_models(out, cache),
            "inference": lambda out: build_inference(out, build_target, cache),
            "maintenance": build_maintenance,
            "base": lambda out: build_base(out, parts),
        }
        rebuilt = set()
        for name in CACHED_STAGES:
            upstream_changed = name == "base" and bool(
                rebuilt.intersection(("runtime", "inference", "models"))
            )
            if build_cached_stage(
                work / name,
                keys[name],
                builders[name],
                force=arguments.force or upstream_changed,
                signed=name in ("runtime", "inference", "maintenance"),
            ):
                rebuilt.add(name)

        with tempfile.TemporaryDirectory(prefix="package-", dir=work) as temporary:
            package_root = Path(temporary)
            parts["application"] = package_root / "application"
            with stage("application"):
                build_application(parts["application"], parts, build_target)
                strip_finder_metadata(parts["application"])
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
                carrier = package(package_root, parts, output, manifest)
        manifest = replace(manifest, installer=artifact(carrier, f"{RELEASES}/{tag}"))
        write_json(
            output / f"distribution-macos-arm64-{EDITION}.json", manifest.to_dict()
        )
        return carrier


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work",
        type=Path,
        default=ROOT / "build/macos-dmg",
        help="empty or previously initialized local build workspace",
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
        "--force", action="store_true", help="rebuild all cached component payloads"
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
