from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .manifest import Manifest, ModelSpec, model_relative_path


def default_user_models_dir() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "").strip()
        root = Path(appdata) if appdata else Path.home() / "AppData/Roaming"
        return root / "MathCraft/models"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "LaTeXSnipper"
            / "MathCraft"
            / "models"
        )
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    data_root = (
        Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    )
    return data_root / "LaTeXSnipper" / "MathCraft" / "models"


def resolve_user_models_dir(cache_dir: str | Path | None = None) -> Path:
    if cache_dir:
        return Path(cache_dir)
    override = os.environ.get("MATHCRAFT_HOME", "").strip()
    if override:
        return Path(override)
    return default_user_models_dir()


def default_cache_dir() -> Path:
    return default_user_models_dir()


def resolve_cache_dir(cache_dir: str | Path | None = None) -> Path:
    return resolve_user_models_dir(cache_dir)


def bundled_models_dir() -> Path | None:
    candidates: list[Path] = []
    env_root = os.environ.get("MATHCRAFT_BUNDLED_MODELS_DIR", "").strip()
    if env_root:
        candidates.append(Path(env_root))
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "MathCraft" / "models")
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "MathCraft" / "models")
        candidates.append(exe_dir / "MathCraft" / "models")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def resolve_model_roots(
    cache_dir: str | Path | None = None,
    bundled_dir: str | Path | None = None,
) -> tuple[Path, ...]:
    roots: list[Path] = []
    bundled = Path(bundled_dir) if bundled_dir else bundled_models_dir()
    if bundled and bundled.is_dir():
        roots.append(bundled)
    user_root = resolve_user_models_dir(cache_dir)
    if user_root not in roots:
        roots.append(user_root)
    return tuple(roots)


@dataclass(frozen=True)
class ModelCacheState:
    model_id: str
    model_dir: Path
    exists: bool
    complete: bool
    missing_files: tuple[str, ...]

    @property
    def broken(self) -> bool:
        return self.exists and not self.complete


def model_dir(root: str | Path, model_id: str) -> Path:
    model_relative_path(model_id)
    return Path(root) / model_id


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_file_valid(root: Path, path: str, sha256: str) -> bool:
    """Validate current bytes; filesystem timestamps cannot identify file content."""
    model_relative_path(path)
    file = root / path
    try:
        if (
            file.is_symlink()
            or not file.resolve(strict=True).is_relative_to(root.resolve())
            or not file.is_file()
        ):
            return False
        return not sha256 or _file_digest(file.resolve()) == sha256
    except (OSError, RuntimeError):
        return False


def inspect_model_cache(root: str | Path, spec: ModelSpec) -> ModelCacheState:
    target = model_dir(root, spec.model_id)
    exists = target.is_dir()
    missing: list[str] = []
    if exists:
        for file_spec in spec.files:
            if not model_file_valid(target, file_spec.path, file_spec.sha256):
                missing.append(file_spec.path)
    else:
        missing = [item.path for item in spec.files]
    return ModelCacheState(
        model_id=spec.model_id,
        model_dir=target,
        exists=exists,
        complete=(exists and not missing),
        missing_files=tuple(missing),
    )


def inspect_model_roots(
    roots: tuple[Path, ...] | list[Path], spec: ModelSpec
) -> ModelCacheState:
    states = []
    for root in roots:
        state = inspect_model_cache(root, spec)
        if state.complete:
            return state
        states.append(state)
    for state in states:
        if state.exists:
            return state
    return states[-1]


def inspect_manifest_cache(
    root: str | Path, manifest: Manifest, include_optional: bool = True
) -> dict[str, ModelCacheState]:
    states: dict[str, ModelCacheState] = {}
    for model_id, spec in manifest.models.items():
        if spec.optional and not include_optional:
            continue
        states[model_id] = inspect_model_cache(root, spec)
    return states


def inspect_manifest_roots(
    roots: tuple[Path, ...] | list[Path],
    manifest: Manifest,
    include_optional: bool = True,
) -> dict[str, ModelCacheState]:
    states: dict[str, ModelCacheState] = {}
    for model_id, spec in manifest.models.items():
        if spec.optional and not include_optional:
            continue
        states[model_id] = inspect_model_roots(roots, spec)
    return states
