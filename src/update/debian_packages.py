"""Construct package-manager payloads exclusively from verified component files."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from runtime.distribution_manifest import Component, ManifestError
from runtime.installation_layout import linux_prefix
from runtime.processes import independent_process_environment


def package_name(name: str) -> str:
    return "latexsnipper" if name == "application" else f"latexsnipper-{name}"


def build_package(
    source: Path, component: Component, output: Path, *, integration: Path | None = None
) -> None:
    """No dependency resolution or network is involved in packaging the payload."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="debian-component-", dir=output.parent
    ) as temporary:
        directory = Path(temporary)
        payload = directory / "usr/lib/latexsnipper" / component.name
        payload.parent.mkdir(parents=True)
        if source.is_symlink():
            raise ManifestError(
                "Package components cannot redirect outside their installation"
            )
        if source.is_dir():

            def link_or_copy(original, destination):
                try:
                    os.link(original, destination)
                except OSError:
                    shutil.copy2(original, destination)
                return destination

            shutil.copytree(source, payload, symlinks=True, copy_function=link_or_copy)
        control = directory / "DEBIAN"
        if component.name == "application":
            integration = (
                integration if integration is not None else source / "linux-integration"
            )
            if not integration.is_dir():
                raise ManifestError(
                    "Application component lacks its owned Linux package integration"
                )
            shutil.copytree(integration, directory, dirs_exist_ok=True, symlinks=True)
            control_path = control / "control"
            text = control_path.read_text(encoding="utf-8").replace(
                "Version: 0.0.0", f"Version: 0+{component.content_sha256}"
            )
            control_path.write_text(text, encoding="utf-8")
        else:
            control.mkdir()
            architecture = {"x86_64": "amd64", "arm64": "arm64", "any": "all"}[
                component.architecture
            ]
            (control / "control").write_text(
                f"Package: {package_name(component.name)}\nVersion: 0+{component.content_sha256}\n"
                f"Architecture: {architecture}\nMaintainer: MathCraft\nSection: utils\nPriority: optional\n"
                "Depends: latexsnipper\n"
                f"Description: LaTeXSnipper {component.name} resource component\n",
                encoding="utf-8",
            )
        # Transaction packages stay local; compression only adds install latency.
        result = subprocess.run(
            [
                "dpkg-deb",
                "--root-owner-group",
                "-Znone",
                "--build",
                str(directory),
                str(output),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
            env=independent_process_environment(),
        )
        if result.returncode:
            raise ManifestError(f"Component package assembly failed: {result.stderr}")


def install_packages(
    root: Path, packages: list[Path], *, resolve_dependencies: bool = False
) -> None:
    if not packages:
        return
    prefix = linux_prefix(root)
    if resolve_dependencies and prefix == Path("/"):
        arguments = [
            "apt-get",
            "install",
            "-y",
            "--no-install-recommends",
            "--reinstall",
            "--allow-downgrades",
        ]
    else:
        arguments = ["dpkg"]
        if prefix != Path("/"):
            arguments += ["--root", str(prefix)]
        arguments.append("--install")
    result = subprocess.run(
        [*arguments, *map(str, packages)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
        env=independent_process_environment(),
    )
    if result.returncode:
        raise ManifestError(
            f"Component package installation failed: {result.stdout}\n{result.stderr}"
        )


def purge_packages(root: Path, names: list[str]) -> None:
    if not names:
        return
    prefix = linux_prefix(root)
    arguments = ["dpkg"]
    if prefix != Path("/"):
        arguments += ["--root", str(prefix)]
    environment = independent_process_environment()
    environment["LATEXSNIPPER_DEPLOYMENT_ACTIVE"] = "1"
    result = subprocess.run(
        [*arguments, "--purge", *[package_name(name) for name in names]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=900,
        env=environment,
    )
    if result.returncode:
        raise ManifestError(
            f"Incomplete first-install package cleanup failed: {result.stderr}"
        )
