"""Fingerprint each cached payload from its own producer inputs."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from distribution_inputs import load_resources, load_sources
from mathcraft_ocr.protocol import MODEL_FORMAT, WORKER_PROTOCOL
from runtime.distribution_manifest import read_json


def source_dependencies(root: Path, entries: list[Path]) -> list[Path]:
    """Follow local Python imports, including lazy imports and package initializers."""
    paths, pending = set(), list(entries)
    while pending:
        path = pending.pop()
        if path in paths or not path.is_file():
            continue
        paths.add(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = node.module or ""
                if node.level:
                    owner = path.parent
                    for _ in range(node.level - 1):
                        owner = owner.parent
                    base = root / "src" if owner.is_relative_to(root / "src") else root
                    prefix = ".".join(
                        (*owner.relative_to(base).parts, *prefix.split("."))
                    ).strip(".")
                names = [prefix, *(f"{prefix}.{alias.name}" for alias in node.names)]
            for name in names:
                for base in (root / "src", root):
                    parts = name.split(".")
                    pending.extend(
                        base.joinpath(*parts[:index], "__init__.py")
                        for index in range(1, len(parts) + 1)
                    )
                    pending.append(base.joinpath(*parts).with_suffix(".py"))
    return sorted(paths)


def fingerprint(root: Path, paths: list[Path], configuration: object) -> str:
    digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode("utf-8"))
    for path in sorted(set(paths)):
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix not in {".pyc", ".pyo"}
        ):
            digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def model_input(root: Path) -> str:
    resources = load_resources(root / "packaging/runtime/resources.lock.json")
    # The normalized model payload is completely specified by these locked bytes.
    return fingerprint(
        root,
        [],
        {
            "layout": 1,
            "models": resources["models"],
            "manifest": resources["model_manifest"],
            "format": resources["model_format"],
            "license": resources["licenses"]["models"],
        },
    )


def build_inputs(root: Path, target: str) -> dict[str, str]:
    resources = load_resources(root / "packaging/runtime/resources.lock.json")
    sources = load_sources(root / "packaging/runtime/sources.lock.json")
    dependencies = read_json(root / "packaging/runtime/dependencies.lock.json")
    system = target.split("-")[0]
    runtime = [
        root / name
        for name in (
            "requirements.txt",
            "requirements-build.txt",
            "LaTeXSnipper.spec",
            "scripts/build_gui_runtime.py",
            "scripts/qt_payload.py",
            "scripts/payload_paths.py",
            "packaging/runtime/gui_entry.py",
            "packaging/runtime/gui-imports.json",
        )
    ] + list((root / "src/assets/MathJax").rglob("*"))
    if system == "windows":
        runtime.append(root / "scripts/normalize_windows_crt.ps1")
    if system == "linux":
        runtime.append(root / "scripts/linux_hotkey_packaging.py")
    keys = {
        "models": model_input(root),
        "runtime": fingerprint(
            root,
            runtime,
            {
                "target": target,
                "python": sources["python_version"],
                "pandoc": resources["pandoc"][target],
                "pandoc_version": resources["pandoc_version"],
                "license": resources["licenses"]["pandoc"],
            },
        ),
    }
    inference = [
        root / name
        for name in (
            "scripts/build_inference_component.py",
            "scripts/payload_pruning.py",
            "scripts/payload_paths.py",
            "src/runtime/inference_probe.py",
        )
    ]
    config = sources["targets"][target]
    for edition in ("cpu",) if system == "macos" else ("cpu", "gpu"):
        settings = {
            "target": target,
            "edition": edition,
            "python": config["python"],
            "ort": config[f"ort_{edition}"],
            "python_version": sources["python_version"],
            "ort_version": sources["ort_version"],
            "dependencies": dependencies["targets"][target],
            "build_tools": dependencies["build_tools"],
            "protocol": WORKER_PROTOCOL,
            "format": MODEL_FORMAT,
        }
        if edition == "gpu":
            settings.update(
                native=config["native_libraries"],
                minimum_driver=config["minimum_driver"],
                cuda=sources["cuda_version"],
                cudnn=sources["cudnn_version"],
            )
        keys[f"inference-{edition}"] = fingerprint(root, inference, settings)
    maintenance = [
        root / "scripts/build_maintenance.spec",
        root / "requirements-build.txt",
    ]
    maintenance += source_dependencies(
        root, [root / "src/maintenance_main.py", root / "src/launcher_main.py"]
    )
    if system == "windows":
        maintenance.append(root / "src/assets/icon.ico")
    requirements = (
        (root / "requirements.txt").read_text(encoding="utf-8")
        if (root / "requirements.txt").exists()
        else ""
    )
    keys["maintenance"] = fingerprint(
        root,
        maintenance,
        {
            "target": target,
            "python": sources["python_version"],
            "requests": [
                line
                for line in requirements.splitlines()
                if line.startswith("requests==")
            ],
        },
    )
    if system == "macos":
        signing = [
            root / "scripts/build_macos_base.py",
            root / "packaging/macos/entitlements.plist",
        ]
        for name in ("runtime", "inference-cpu", "maintenance"):
            keys[name] = fingerprint(root, signing, keys[name])
        keys["base"] = fingerprint(
            root,
            [
                root / name
                for name in (
                    "scripts/build_macos_base.py",
                    "packaging/macos/entitlements.plist",
                    "packaging/macos/launcher.c",
                )
            ],
            {name: keys[name] for name in ("runtime", "inference-cpu", "models")},
        )
    return keys
