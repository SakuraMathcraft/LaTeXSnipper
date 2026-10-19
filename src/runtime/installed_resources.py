"""Resolve immutable installation resources and the developer's current Python."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from mathcraft_ocr.protocol import MODEL_FORMAT, WORKER_PROTOCOL
from runtime.component_inventory import verify_component
from runtime.distribution_manifest import (
    DistributionManifest,
    ManifestError,
    read_json,
    safe_relative_path,
)
from runtime.installation_layout import installation_manifest


def installation_root(executable: Path) -> Path:
    executable = executable.resolve()
    if sys.platform == "darwin":
        for parent in executable.parents:
            if parent.name == "LaTeXSnipperBase.bundle":
                return parent.parent.parent / "Resources/desktop"
    return executable.parent.parent


def current_target() -> tuple[str, str]:
    system = {"win32": "windows", "linux": "linux", "darwin": "macos"}[sys.platform]
    machine = platform.machine().lower()
    architectures = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    if machine not in architectures:
        raise ManifestError(f"Unsupported runtime architecture: {machine}")
    return system, architectures[machine]


@dataclass(frozen=True)
class InstalledResources:
    root: Path
    manifest: DistributionManifest

    @classmethod
    def load(cls, root: Path) -> InstalledResources:
        root = root.resolve()
        if any(
            (root / name).is_symlink()
            for name in (
                "application",
                "runtime",
                "inference",
                "models",
                "distribution.json",
            )
        ):
            raise ManifestError(
                "Installation components must not redirect outside the installation"
            )
        metadata = installation_manifest(root, current_target()[0])
        if metadata.is_symlink():
            raise ManifestError(
                "Installation metadata must not redirect outside its owner"
            )
        manifest = DistributionManifest.load(metadata)
        if (manifest.platform, manifest.architecture) != current_target():
            raise ManifestError("Installed distribution does not match this platform")
        if (
            manifest.application.worker_protocol != WORKER_PROTOCOL
            or manifest.application.model_format != MODEL_FORMAT
        ):
            raise ManifestError(
                "Installed resources are incompatible with this application"
            )
        return cls(root, manifest)

    def directory(self, component: str) -> Path:
        if component not in {"application", "runtime", "inference", "models"}:
            raise ManifestError("Unknown installation resource")
        if self.manifest.platform == "macos" and component != "application":
            from runtime.installation_layout import macos_bundle

            return (
                macos_bundle(self.root)
                / "Contents/Frameworks/LaTeXSnipperBase.bundle/Contents/Resources"
                / component
            )
        return self.root / component

    def resource(self, component: str, relative: str) -> Path:
        declared = self.directory(component)
        directory = declared.resolve(strict=True)
        owner = self.root
        if self.manifest.platform == "macos":
            from runtime.installation_layout import macos_bundle

            owner = macos_bundle(self.root)
        if declared.is_symlink() or not directory.is_relative_to(owner):
            raise ManifestError("Installation resource directory escaped its owner")
        path = directory / safe_relative_path(relative)
        if (
            not path.resolve(strict=True).is_relative_to(directory)
            or not path.is_file()
        ):
            raise ManifestError(
                f"Installed resource is missing or unsafe: {component}/{relative}; rerun the full installer"
            )
        return path

    @property
    def python(self) -> Path:
        relative = (
            "python.exe" if self.manifest.platform == "windows" else "bin/python3"
        )
        return self.resource("inference", relative)

    def verify_runtime(self) -> None:
        details = read_json(self.resource("inference", "runtime.json"))
        expected = {
            "schema": 1,
            "target": f"{self.manifest.platform}-{self.manifest.architecture}",
            "edition": self.manifest.edition,
            "worker_protocol": WORKER_PROTOCOL,
            "model_format": MODEL_FORMAT,
        }
        if any(
            type(details.get(key)) is not type(value) or details[key] != value
            for key, value in expected.items()
        ):
            raise ManifestError(
                "Inference runtime does not match the installation contract"
            )
        _ = self.python
        application = self.manifest.application
        worker_files = tuple(
            record for record in application.files if record.path.startswith("worker/")
        )
        required = {
            f"worker/mathcraft_ocr/{name}.py"
            for name in ("worker", "protocol", "runtime")
        }
        if not required <= {record.path for record in worker_files} or verify_component(
            self.root / "application",
            replace(application, files=worker_files),
            exact=False,
        ):
            raise ManifestError("Installed worker implementation is missing or corrupt")
        self.resource("models", "models.v1.json")


def installed_resources() -> InstalledResources | None:
    if not getattr(sys, "frozen", False):
        return None
    return InstalledResources.load(installation_root(Path(sys.executable)))


def worker_environment(resources: InstalledResources | None) -> dict[str, str]:
    env = os.environ.copy()
    for key in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONUSERBASE",
        "PYTHONSTARTUP",
        "PYTHONEXECUTABLE",
        "MATHCRAFT_HOME",
        "MATHCRAFT_BUNDLED_MODELS_DIR",
        "CUDA_PATH",
        "CUDA_HOME",
    ):
        env.pop(key, None)
    env.update(
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
        PYTHONFAULTHANDLER="1",
    )
    if resources is not None:
        root = resources.directory("inference")
        if resources.manifest.platform == "windows":
            system_root = env.get("SYSTEMROOT") or env.get("SystemRoot")
            if not system_root:
                raise ManifestError("Windows system directory is unavailable")
            env["PATH"] = os.pathsep.join(
                [str(root / "native"), str(root), str(Path(system_root) / "System32")]
            )
        elif resources.manifest.platform == "linux":
            env["LD_LIBRARY_PATH"] = os.pathsep.join(
                [str(root / "native"), str(root / "lib")]
            )
            env.pop("LD_PRELOAD", None)
        else:
            for key in tuple(env):
                if key.startswith("DYLD_"):
                    env.pop(key)
    return env


def worker_command(resources: InstalledResources | None) -> list[str]:
    from runtime.model_resources import desktop_model_resources

    if resources is None:
        root = Path(__file__).resolve().parents[2]
        python = Path(sys.executable)
        arguments = {
            "provider_preference": "cpu",
            "cache_dir": str(desktop_model_resources(None).root),
        }
    else:
        resources.verify_runtime()
        models = desktop_model_resources(resources)
        root = resources.root / "application" / "worker"
        python = resources.python
        arguments = {
            "provider_preference": "cuda"
            if resources.manifest.edition == "gpu"
            else "cpu",
            "models_dir": str(models.root),
            "manifest_path": str(models.manifest_path),
            "cache_dir": str(models.root),
            "auto_download": False,
        }
        if resources.manifest.edition == "gpu":
            arguments["native_dir"] = str(resources.directory("inference") / "native")
    prefix = ""
    if os.name == "nt":
        prefix = "import ctypes; ctypes.windll.kernel32.SetDllDirectoryW(None); "
        if resources is not None:
            native = resources.directory("inference") / "native"
            prefix += f"import os; _dll_handles=[os.add_dll_directory({str(python.parent)!r})]; "
            if resources.manifest.edition == "gpu":
                prefix += (
                    f"_dll_handles.append(os.add_dll_directory({str(native)!r})); "
                )
    code = (
        prefix
        + f"import sys; sys.path.insert(0, {str(root)!r}); from mathcraft_ocr.worker import serve_jsonl; raise SystemExit(serve_jsonl(**{arguments!r}))"
    )
    return [str(python), "-I", "-B", "-u", "-X", "utf8", "-c", code]
