"""Build the three desktop components and native offline carriers in GitHub Actions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import sys
import tempfile
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from desktop_distribution import write_json  # noqa: E402
from distribution_inputs import load_resources, load_sources  # noqa: E402
from release_artifacts import (  # noqa: E402
    artifact,
    finalize_windows,
    package_bundle_seal,
    package_component,
    publish_catalog,
)
from release_installers import (  # noqa: E402
    link_or_copy,
    linux_installer,
    macos_installer,
    run,
    windows_installer,
)
from runtime.component_archive import extract_archive  # noqa: E402
from runtime.component_inventory import verify_component  # noqa: E402
from runtime.distribution_manifest import (  # noqa: E402
    Component,
    DistributionManifest,
    ManifestError,
    read_json,
)
from runtime.installed_resources import current_target  # noqa: E402
from update.deployment_transaction import verify_distribution  # noqa: E402
from update.deployment_validation import validate_installed_worker  # noqa: E402


def fingerprint(paths: list[Path], configuration: object) -> str:
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode())
    for path in sorted(set(paths)):
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        ):
            digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def build_inputs(target: str) -> dict[str, str]:
    resources = load_resources(ROOT / "packaging/runtime/resources.lock.json")
    application = list((ROOT / "src").rglob("*")) + list(
        (ROOT / "mathcraft_ocr").rglob("*.py")
    )
    application.append(ROOT / "mathcraft_ocr/vendor/LICENSE.onnx")
    system = target.split("-")[0]
    requirements = {
        "windows": "requirements.txt",
        "linux": "requirements-linux.txt",
        "macos": "requirements-macos.txt",
    }[system]
    application += [
        ROOT / name
        for name in (
            requirements,
            "requirements-build.txt",
            {
                "windows": "LaTeXSnipper.spec",
                "linux": "LaTeXSnipper-linux.spec",
                "macos": "LaTeXSnipper-macos.spec",
            }[target.split("-")[0]],
            "LICENSE",
        )
    ]
    application += [
        ROOT / "scripts/build_application_resources.py",
        ROOT / "scripts/build_maintenance.spec",
        ROOT / "scripts/build_desktop_release.py",
        ROOT / "scripts/build_desktop_resources.py",
        ROOT / "scripts/distribution_archives.py",
        ROOT / "scripts/distribution_inputs.py",
        ROOT / "scripts/payload_pruning.py",
    ]
    if target.startswith("windows-"):
        application.append(ROOT / "scripts/normalize_windows_crt.ps1")
    if target.startswith("linux-"):
        application += [
            ROOT / "scripts/linux_hotkey_packaging.py",
            ROOT / "scripts/latexsnipper-clean-user-data.sh",
        ]
        application += list((ROOT / "packaging/debian").rglob("*"))
    sources = load_sources(ROOT / "packaging/runtime/sources.lock.json")
    inference = [
        ROOT / "packaging/runtime/dependencies.lock.json",
        ROOT / "scripts/build_inference_component.py",
        ROOT / "scripts/payload_pruning.py",
        ROOT / "scripts/distribution_archives.py",
        ROOT / "scripts/distribution_inputs.py",
        ROOT / "mathcraft_ocr/protocol.py",
        ROOT / "src/runtime/inference_probe.py",
        ROOT / "src/runtime/component_inventory.py",
        ROOT / "src/runtime/component_archive.py",
        ROOT / "src/runtime/distribution_manifest.py",
        ROOT / "src/runtime/processes.py",
        ROOT / "scripts/build_desktop_release.py",
    ]
    if target.startswith("macos-"):
        application.append(ROOT / "packaging/macos/entitlements.plist")
        inference.append(ROOT / "packaging/macos/entitlements.plist")
    return {
        "application": fingerprint(
            application, {"target": target, "pandoc": resources["pandoc"][target]}
        ),
        "inference": fingerprint(
            inference,
            {
                "target": target,
                "sources": sources["targets"][target],
                "versions": {
                    key: sources[key]
                    for key in (
                        "python_version",
                        "ort_version",
                        "cuda_version",
                        "cudnn_version",
                    )
                },
            },
        ),
    }


def cached_payload(work: Path, name: str, key: str) -> Path | None:
    directory = work / name
    stamp = directory / "stamp.json"
    if stamp.is_file():
        saved = read_json(stamp)
        component = Component.from_dict(saved["component"])
        if saved["input"] != key or verify_component(directory / "payload", component):
            raise ManifestError(
                f"Cached build failed its input or inventory check: {name}"
            )
        return directory / "payload"
    if directory.exists():
        raise ManifestError(f"Incomplete cached build: {name}")
    return None


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


def validate_windows_signatures(directory: Path) -> None:
    script = """param([string]$Root)
$ErrorActionPreference = 'Stop'
Get-ChildItem -LiteralPath $Root -Recurse -File | Where-Object { $_.Extension -in '.exe', '.dll', '.pyd' } | ForEach-Object {
    $signature = Get-AuthenticodeSignature -LiteralPath $_.FullName
    if ($signature.Status -ne 'Valid') { throw "Untrusted Windows executable: $($_.FullName) $($signature.Status)" }
}
"""
    with tempfile.TemporaryDirectory(prefix="signature-check-") as temporary:
        path = Path(temporary) / "verify.ps1"
        path.write_text(script, encoding="utf-8")
        run(["pwsh", "-NoProfile", "-File", path, directory])


def assemble(args) -> None:
    from build_application_resources import assemble as assemble_application
    from build_inference_component import assemble as assemble_inference

    target = "-".join(current_target())
    keys = build_inputs(target)
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if cached_payload(work, "application", keys["application"]) is None:
        build = work / "application"
        build.mkdir()
        spec = {
            "windows": "LaTeXSnipper.spec",
            "linux": "LaTeXSnipper-linux.spec",
            "macos": "LaTeXSnipper-macos.spec",
        }[current_target()[0]]
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--distpath",
                build / "frozen",
                "--workpath",
                build / "pyinstaller",
                ROOT / spec,
            ]
        )
        (build / "frozen/LaTeXSnipper").rename(build / "payload")
        run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--noconfirm",
                "--distpath",
                build / "maintenance",
                "--workpath",
                build / "maintenance-work",
                ROOT / "scripts/build_maintenance.spec",
            ]
        )
        executable = ".exe" if current_target()[0] == "windows" else ""
        shutil.copy2(
            build / "maintenance" / f"updater{executable}",
            build / "payload" / f"updater{executable}",
        )
        (build / "payload/bootstrap").mkdir()
        shutil.copy2(
            build / "maintenance" / f"LaTeXSnipper{executable}",
            build / "payload/bootstrap" / f"LaTeXSnipper{executable}",
        )
        assemble_application(
            Namespace(
                application=build / "payload",
                target=target,
                cache=args.cache,
                lock=ROOT / "packaging/runtime/resources.lock.json",
            )
        )
        if current_target()[0] == "windows":
            run(
                [
                    "pwsh",
                    "-NoProfile",
                    "-File",
                    ROOT / "scripts/normalize_windows_crt.ps1",
                    "-DistributionRoot",
                    build / "payload",
                ]
            )
        for directory in ("frozen", "pyinstaller", "maintenance", "maintenance-work"):
            shutil.rmtree(build / directory)
        if current_target()[0] == "macos":
            sign_macos_tree(build / "payload")
    for edition in ("cpu", "gpu") if current_target()[0] != "macos" else ("cpu",):
        name = f"inference-{edition}"
        if cached_payload(work, name, keys["inference"]) is None:
            (work / name).mkdir()
            assemble_inference(
                Namespace(
                    target=target,
                    edition=edition,
                    output=work / name / "payload",
                    cache=args.cache,
                    catalog=ROOT / "packaging/runtime/sources.lock.json",
                    dependencies=ROOT / "packaging/runtime/dependencies.lock.json",
                    validate_gpu=False,
                )
            )
            if current_target()[0] == "macos":
                sign_macos_tree(work / name / "payload")


def create_macos_bundle(layout: Path, manifest: DistributionManifest) -> Path:
    from distribution_inputs import load_dependencies, macos_minimum_version

    sources = load_sources(ROOT / "packaging/runtime/sources.lock.json")
    dependencies = load_dependencies(
        ROOT / "packaging/runtime/dependencies.lock.json", sources
    )
    minimum_version = macos_minimum_version(sources, dependencies)
    bundle = layout.parent / "LaTeXSnipper.app"
    desktop = bundle / "Contents/Resources/desktop"
    desktop.parent.mkdir(parents=True)
    shutil.copytree(layout, desktop, symlinks=True)
    (bundle / "Contents/MacOS").mkdir()
    run(
        [
            "clang",
            f"-mmacosx-version-min={minimum_version}",
            "-O2",
            ROOT / "packaging/macos/launcher.c",
            "-o",
            bundle / "Contents/MacOS/LaTeXSnipper",
        ]
    )
    plist = {
        "CFBundleName": "LaTeXSnipper",
        "CFBundleDisplayName": "LaTeXSnipper",
        "CFBundleIdentifier": "com.mathcraft.latexsnipper",
        "CFBundleExecutable": "LaTeXSnipper",
        "CFBundlePackageType": "APPL",
        "CFBundleVersion": manifest.version,
        "CFBundleShortVersionString": manifest.version,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": minimum_version,
        "NSPrincipalClass": "NSApplication",
        "NSHumanReadableCopyright": "Copyright 2026 MathCraft",
    }
    for folder in (
        "Desktop",
        "Documents",
        "Downloads",
        "NetworkVolumes",
        "RemovableVolumes",
    ):
        plist[
            f"NS{folder}FolderUsageDescription"
            if folder in ("Desktop", "Documents", "Downloads")
            else f"NS{folder}UsageDescription"
        ] = "LaTeXSnipper accesses files you choose for recognition and export."
    with (bundle / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump(plist, stream)
    iconset = layout.parent / "latexsnipper.iconset"
    iconset.mkdir()
    from PIL import Image

    image = Image.open(ROOT / "src/assets/icon.ico").convert("RGBA")
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            suffix = "@2x" if scale == 2 else ""
            image.resize((size * scale, size * scale), Image.Resampling.LANCZOS).save(
                iconset / f"icon_{size}x{size}{suffix}.png"
            )
    run(
        [
            "iconutil",
            "-c",
            "icns",
            iconset,
            "-o",
            bundle / "Contents/Resources/icon.icns",
        ]
    )
    plist["CFBundleIconFile"] = "icon.icns"
    with (bundle / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump(plist, stream)
    run(["codesign", "--force", "--sign", "-", bundle / "Contents/MacOS/LaTeXSnipper"])
    run(["codesign", "--force", "--sign", "-", bundle])
    from update.macos_transaction import verify_bundle

    verify_bundle(bundle)
    return bundle


def package(args) -> None:
    system, architecture = current_target()
    target = f"{system}-{architecture}"
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    release_tag = args.tag or f"v{version}"
    base_url = f"https://github.com/SakuraMathcraft/LaTeXSnipper/releases/download/{release_tag}"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work = args.work.resolve()
    keys = build_inputs(target)
    application = package_component(
        work / "application/payload", output, "application", target, "common", base_url
    )
    write_json(
        work / "application/stamp.json",
        {"input": keys["application"], "component": application.to_dict()},
    )
    models = Component.from_dict(read_json(args.models / "models.component.json"))
    damaged_models = verify_component(args.models / "payload", models)
    if damaged_models:
        raise ManifestError(
            "Common model artifact failed its inventory validation: "
            + ", ".join(damaged_models)
        )
    model_archive = args.models / Path(models.artifact.url).name
    if artifact(model_archive, base_url) != models.artifact:
        raise ManifestError("Common models do not belong to the current release")
    shutil.copy2(model_archive, output / model_archive.name)
    for edition in ("cpu", "gpu") if system != "macos" else ("cpu",):
        source = work / f"inference-{edition}/payload"
        inference = package_component(
            source, output, "inference", target, edition, base_url
        )
        write_json(
            work / f"inference-{edition}/stamp.json",
            {"input": keys["inference"], "component": inference.to_dict()},
        )
        manifest = DistributionManifest(
            version,
            system,
            architecture,
            edition,
            (application, inference, models),
            release_tag=release_tag,
        )
        prefix = work / f"layout-{edition}"
        layout = prefix / "usr/lib/latexsnipper" if system == "linux" else prefix
        layout.mkdir(parents=True)
        for component, directory in (
            (application, work / "application/payload"),
            (inference, source),
            (models, args.models / "payload"),
        ):
            shutil.copytree(
                directory,
                layout / component.name,
                symlinks=True,
                copy_function=link_or_copy,
            )
        executable = "LaTeXSnipper.exe" if system == "windows" else "LaTeXSnipper"
        shutil.copy2(layout / "application/bootstrap" / executable, layout / executable)
        write_json(
            layout / "distribution.json", manifest.installed_identity().to_dict()
        )
        if system == "linux":
            write_json(
                prefix / "var/lib/latexsnipper/distribution.json",
                manifest.installed_identity().to_dict(),
            )
        verify_distribution(layout, manifest)
        validate_installed_worker(layout, manifest)
        # Launch a relocated frozen application. Source-import checks cannot
        # prove that Qt WebEngine, PDF and XML payloads survived freezing.
        if edition == "cpu":
            env = os.environ.copy()
            env["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"
            if system == "linux":
                env["QT_QPA_PLATFORM"] = "offscreen"
            run(
                [
                    layout / "application" / executable,
                    "--validate-application",
                    work / "application-validation.json",
                ],
                env=env,
                timeout=180,
            )
        if system == "windows":
            carrier = windows_installer(layout, output, manifest)
        elif system == "linux":
            carrier = linux_installer(layout, output, manifest)
        else:
            bundle = create_macos_bundle(layout, manifest)
            seal = package_bundle_seal(
                bundle, output / f"bundle-seal-macos-arm64-{version}.zip", base_url
            )
            manifest = replace(manifest, bundle_seal=seal)
            # Prove that independently archived components reconstruct the
            # same bundle with valid local code signatures.
            reconstructed = work / "reconstructed/LaTeXSnipper.app"
            extract_archive(
                output / Path(seal.artifact.url).name, reconstructed, component=seal
            )
            for component in manifest.components:
                extract_archive(
                    output / Path(component.artifact.url).name,
                    reconstructed / "Contents/Resources/desktop" / component.name,
                    component=component,
                )
            from update.macos_transaction import verify_bundle

            verify_bundle(reconstructed)
            carrier = macos_installer(bundle, output, manifest)
        manifest = replace(manifest, installer=artifact(carrier, base_url))
        write_json(
            output / f"distribution-{system}-{architecture}-{edition}.json",
            manifest.to_dict(),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "inputs",
            "models",
            "assemble",
            "package",
            "finalize-windows",
            "catalog",
        ),
    )
    parser.add_argument("--work", type=Path, default=ROOT / "build/desktop")
    parser.add_argument("--cache", type=Path, default=ROOT / "build/downloads")
    parser.add_argument("--models", type=Path, default=ROOT / "build/common-models")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/desktop")
    parser.add_argument("--signed", type=Path)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    if args.command == "inputs":
        keys = build_inputs("-".join(current_target()))
        print(json.dumps(keys))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
                for name, key in keys.items():
                    stream.write(f"{name}={key}\n")
        return
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ManifestError("Desktop installers must be built by GitHub Actions")
    if args.command == "models":
        from build_desktop_resources import assemble as assemble_resources

        args.models.mkdir(parents=True, exist_ok=True)
        assemble_resources(
            Namespace(
                resource="models",
                target=None,
                output=args.models / "payload",
                cache=args.cache,
                lock=ROOT / "packaging/runtime/resources.lock.json",
            )
        )
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        tag = args.tag or f"v{version}"
        component = package_component(
            args.models / "payload",
            args.models,
            "models",
            "any-any",
            "common",
            f"https://github.com/SakuraMathcraft/LaTeXSnipper/releases/download/{tag}",
        )
        write_json(args.models / "models.component.json", component.to_dict())
    elif args.command == "assemble":
        assemble(args)
    elif args.command == "package":
        package(args)
    elif args.command == "finalize-windows":
        validate_windows_signatures(args.signed)
        finalize_windows(args.output, args.signed)
    else:
        publish_catalog(
            args.output,
            (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            args.output / "desktop-release.json",
        )


if __name__ == "__main__":
    main()
