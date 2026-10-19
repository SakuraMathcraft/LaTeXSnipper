"""Build business updates and assemble offline installers from persistent fixed resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import sys
from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from desktop_distribution import write_json  # noqa: E402
from distribution_inputs import load_sources  # noqa: E402
from release_artifacts import (  # noqa: E402
    artifact,
    finalize_windows,
    package_component,
    upload_desktop_assets,
)
from release_build_inputs import build_inputs as resource_inputs  # noqa: E402
from release_build_inputs import model_input  # noqa: E402
from release_installers import (  # noqa: E402
    link_or_copy,
    linux_installer,
    macos_installer,
    run,
    windows_installer,
)
from runtime.component_archive import extract_archive  # noqa: E402
from runtime.distribution_manifest import (  # noqa: E402
    Component,
    DistributionManifest,
    ManifestError,
    read_json,
)
from runtime.installation_layout import macos_bundle  # noqa: E402
from runtime.installed_resources import current_target  # noqa: E402


def build_inputs(target: str) -> dict[str, str]:
    return resource_inputs(ROOT, target)


def outputs(values: dict) -> None:
    print(json.dumps(values))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            for name, value in values.items():
                stream.write(
                    f"{name}={str(value).lower() if isinstance(value, bool) else value}\n"
                )


def plan_build(args) -> dict:
    from desktop_base_cache import cache_tag, exists

    target = "-".join(current_target())
    keys = build_inputs(target)
    names = (
        ["base", "maintenance"]
        if target.startswith("macos-")
        else ["runtime", "inference-cpu", "inference-gpu", "models", "maintenance"]
    )
    available = {}

    def check(name):
        return name, exists(
            cache_tag(name, "any-any" if name == "models" else target, keys[name])
        )

    with ThreadPoolExecutor(max_workers=5) as probes:
        available.update(probes.map(check, names))
        if "base" in available and not available["base"]:
            available.update(probes.map(check, ["runtime", "inference-cpu", "models"]))
    plan = {"schema": 1, "target": target, "keys": keys, "available": available}
    write_json(args.plan, plan)
    missing = {name for name, cached in available.items() if not cached}
    outputs(
        {
            "gui_missing": "runtime" in missing,
            "maintenance_missing": "maintenance" in missing,
            "native_missing": bool(
                missing & {"runtime", "inference-cpu", "inference-gpu"}
            ),
        }
    )
    return plan


def load_plan(args) -> dict:
    if not args.plan.is_file():
        return plan_build(args)
    plan = read_json(args.plan)
    if (
        set(plan) != {"schema", "target", "keys", "available"}
        or plan["schema"] != 1
        or plan["target"] != "-".join(current_target())
    ):
        raise ManifestError("Invalid build plan")
    if (
        not isinstance(plan["keys"], dict)
        or not isinstance(plan["available"], dict)
        or any(type(value) is not bool for value in plan["available"].values())
    ):
        raise ManifestError("Invalid build cache decisions")
    return plan


def cached_payload(work: Path, name: str, key: str) -> Path | None:
    directory = work / name
    stamp = directory / "stamp.json"
    if stamp.is_file():
        saved = read_json(stamp)
        component = Component.from_dict(saved["component"])
        archive = directory / component.artifact.url.rsplit("/", 1)[-1]
        base_url = component.artifact.url.rsplit("/", 1)[0]
        if saved["input"] != key or artifact(archive, base_url) != component.artifact:
            raise ManifestError(
                f"Cached build failed its input or inventory check: {name}"
            )
        payload = directory / "payload"
        extract_archive(archive, payload, component=component)
        return payload
    if directory.exists():
        raise ManifestError(f"Incomplete cached build: {name}")
    return None


def reuse_payload(args, name: str, key: str, build, *, available: bool) -> Path:
    from desktop_base_cache import cache_tag, restore, store

    target = "-".join(current_target()) if name != "models" else "any-any"
    tag = cache_tag(name, target, key)
    directory = args.work.resolve() / name
    if not directory.exists() and available:
        restore(directory, tag)
    payload = cached_payload(args.work.resolve(), name, key)
    if payload is not None:
        return payload
    directory.mkdir(parents=True)
    payload = directory / "payload"
    build(payload)
    if current_target()[0] == "macos" and name in {
        "runtime",
        "inference-cpu",
        "maintenance",
    }:
        from build_macos_base import sign_macos_tree

        sign_macos_tree(payload)
    component = package_component(
        payload,
        directory,
        name.split("-")[0],
        target,
        name.split("-", 1)[1] if name.startswith("inference-") else "common",
        f"https://github.com/SakuraMathcraft/LaTeXSnipper/releases/download/{tag}",
    )
    write_json(
        directory / "stamp.json", {"input": key, "component": component.to_dict()}
    )
    store(directory, tag)
    return payload


def build_maintenance(payload: Path) -> None:
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
            ROOT / "scripts/build_maintenance.spec",
        ]
    )
    payload.mkdir()
    (payload / "bootstrap").mkdir()
    extension = ".exe" if current_target()[0] == "windows" else ""
    shutil.copy2(
        build / "frozen" / f"updater{extension}", payload / f"updater{extension}"
    )
    shutil.copy2(
        build / "frozen" / f"LaTeXSnipper{extension}",
        payload / "bootstrap" / f"LaTeXSnipper{extension}",
    )
    for name in ("frozen", "pyinstaller"):
        shutil.rmtree(build / name)


def build_models(payload: Path, cache: Path) -> None:
    from build_desktop_resources import assemble as assemble_resources

    assemble_resources(
        Namespace(
            resource="models",
            target=None,
            output=payload,
            cache=cache,
            lock=ROOT / "packaging/runtime/resources.lock.json",
        )
    )


def assemble(args) -> None:
    from build_application_resources import assemble as assemble_application

    plan = load_plan(args)
    keys, available = plan["keys"], plan["available"]
    target = plan["target"]
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    parts = {}

    def build_runtime(payload):
        from build_gui_runtime import build_gui_runtime

        build_gui_runtime(payload, target, args.cache)

    def build_inference(payload, edition):
        from build_inference_component import assemble as assemble_inference

        assemble_inference(
            Namespace(
                target=target,
                edition=edition,
                output=payload,
                cache=args.cache,
                catalog=ROOT / "packaging/runtime/sources.lock.json",
                dependencies=ROOT / "packaging/runtime/dependencies.lock.json",
                validate_gpu=False,
            )
        )

    def build_base(payload):
        from build_macos_base import build_macos_base

        build_macos_base(
            payload, parts["runtime"], parts["inference-cpu"], parts["models"]
        )

    builders = {
        "runtime": build_runtime,
        "models": lambda payload: build_models(payload, args.cache),
        "inference-cpu": lambda payload: build_inference(payload, "cpu"),
        "inference-gpu": lambda payload: build_inference(payload, "gpu"),
        "maintenance": build_maintenance,
        "base": build_base,
    }

    def reuse(name):
        owner = Namespace(work=args.models) if name == "models" else args
        return name, reuse_payload(
            owner, name, keys[name], builders[name], available=available[name]
        )

    # Warm builds restore independent archives in parallel. Cold builds are
    # serialized to reuse shared downloads and limit peak memory usage.
    with ThreadPoolExecutor(max_workers=5) as restorers:
        parts.update(
            restorers.map(reuse, [name for name in available if available[name]])
        )
    for name in available:
        if not available[name] and name != "base":
            key, payload = reuse(name)
            parts[key] = payload
    if "base" in available and not available["base"]:
        key, payload = reuse("base")
        parts[key] = payload
    application = work / "application/payload"
    assemble_application(Namespace(application=application, target=target))
    shutil.copytree(
        parts["maintenance"], application, dirs_exist_ok=True, symlinks=True
    )


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
    shutil.copytree(layout, desktop, symlinks=True, copy_function=link_or_copy)
    framework = bundle / "Contents/Frameworks"
    framework.mkdir()
    (desktop / "LaTeXSnipperBase.bundle").rename(framework / "LaTeXSnipperBase.bundle")
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
    application = package_component(
        work / "application/payload", output, "application", target, "common", base_url
    )
    models = args.models / "models/payload"

    def package_edition(edition: str) -> None:
        if system == "macos":
            base_id = Component.from_dict(
                read_json(work / "base/stamp.json")["component"]
            ).content_sha256
        else:
            source = work / f"inference-{edition}/payload"
            base_id = hashlib.sha256(
                json.dumps(
                    {
                        "runtime": Component.from_dict(
                            read_json(work / "runtime/stamp.json")["component"]
                        ).content_sha256,
                        "inference": Component.from_dict(
                            read_json(source.parent / "stamp.json")["component"]
                        ).content_sha256,
                        "models": Component.from_dict(
                            read_json(args.models / "models/stamp.json")["component"]
                        ).content_sha256,
                        "edition": edition,
                    },
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
        manifest = DistributionManifest(
            version,
            system,
            architecture,
            edition,
            application,
            base_id,
            release_tag=release_tag,
        )
        prefix = work / f"layout-{edition}"
        layout = prefix / "usr/lib/latexsnipper" if system == "linux" else prefix
        layout.mkdir(parents=True)
        directories = [("application", work / "application/payload")]
        if system == "macos":
            directories.append(
                (
                    "LaTeXSnipperBase.bundle",
                    work / "base/payload/LaTeXSnipperBase.bundle",
                )
            )
        else:
            directories.extend(
                (
                    ("runtime", work / "runtime/payload"),
                    ("inference", work / f"inference-{edition}/payload"),
                    ("models", models),
                )
            )
        for name, directory in directories:
            shutil.copytree(
                directory, layout / name, symlinks=True, copy_function=link_or_copy
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
        if system == "macos":
            layout = (
                create_macos_bundle(layout, manifest) / "Contents/Resources/desktop"
            )
        if system == "windows":
            carrier = windows_installer(layout, output, manifest)
        elif system == "linux":
            carrier = linux_installer(layout, output, manifest)
        else:
            carrier = macos_installer(macos_bundle(layout), output, manifest)
        manifest = replace(manifest, installer=artifact(carrier, base_url))
        write_json(
            output / f"distribution-{system}-{architecture}-{edition}.json",
            manifest.to_dict(),
        )

    editions = ("cpu", "gpu") if system != "macos" else ("cpu",)
    with ThreadPoolExecutor(max_workers=len(editions)) as packagers:
        list(packagers.map(package_edition, editions))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "inputs",
            "models",
            "models-plan",
            "plan",
            "assemble",
            "package",
            "finalize-windows",
            "upload",
        ),
    )
    parser.add_argument("--work", type=Path, default=ROOT / "build/desktop")
    parser.add_argument("--cache", type=Path, default=ROOT / "build/downloads")
    parser.add_argument("--models", type=Path, default=ROOT / "build/common-models")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/desktop")
    parser.add_argument("--signed", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--tag", default="")
    args = parser.parse_args()
    args.plan = args.plan or args.work / "plan.json"
    if args.command == "inputs":
        keys = build_inputs("-".join(current_target()))
        print(json.dumps(keys))
        return
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ManifestError("Desktop installers must be built by GitHub Actions")
    if args.command == "plan":
        plan_build(args)
    elif args.command in {"models", "models-plan"}:
        from desktop_base_cache import cache_tag, exists

        key = model_input(ROOT)
        available = exists(cache_tag("models", "any-any", key))
        if args.command == "models-plan":
            outputs({"models_missing": not available})
        else:
            args.work = args.models
            reuse_payload(
                args,
                "models",
                key,
                lambda payload: build_models(payload, args.cache),
                available=available,
            )
    elif args.command == "assemble":
        assemble(args)
    elif args.command == "package":
        package(args)
    elif args.command == "finalize-windows":
        finalize_windows(args.output, args.signed)
    elif args.command == "upload":
        upload_desktop_assets(args.output, args.tag)


if __name__ == "__main__":
    main()
