# coding: utf-8

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ManifestError


@dataclass(frozen=True)
class ModelFileSpec:
    path: str
    sha256: str = ""


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    version: str
    files: tuple[ModelFileSpec, ...]
    sources: tuple[str, ...]
    runtime: str = "onnx"
    optional: bool = False


@dataclass(frozen=True)
class Manifest:
    version: int
    models: dict[str, ModelSpec]


def _manifest_path() -> Path:
    return Path(__file__).with_name("manifests") / "models.v1.json"


def _require_dict(raw: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ManifestError(f"manifest field '{field_name}' must be an object")
    return raw


def load_manifest(path: str | Path | None = None) -> Manifest:
    manifest_path = Path(path) if path else _manifest_path()
    raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    raw = _require_dict(raw, "root")
    version = raw.get("version")
    if not isinstance(version, int):
        raise ManifestError("manifest version must be an integer")
    raw_models = _require_dict(raw.get("models"), "models")
    models: dict[str, ModelSpec] = {}
    for model_id, payload in raw_models.items():
        payload = _require_dict(payload, model_id)
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise ManifestError(f"model '{model_id}' must define non-empty files")
        parsed_files: list[ModelFileSpec] = []
        for item in files:
            item = _require_dict(item, f"{model_id}.files")
            model_path = item.get("path")
            if not isinstance(model_path, str) or not model_path.strip():
                raise ManifestError(f"model '{model_id}' file path must be a string")
            sha256 = item.get("sha256", "")
            if sha256 is None:
                sha256 = ""
            if not isinstance(sha256, str):
                raise ManifestError(f"model '{model_id}' file sha256 must be a string")
            parsed_files.append(ModelFileSpec(path=model_path, sha256=sha256))
        sources = payload.get("sources", [])
        if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
            raise ManifestError(f"model '{model_id}' sources must be a list[str]")
        version_text = payload.get("version", "1")
        if not isinstance(version_text, str):
            raise ManifestError(f"model '{model_id}' version must be a string")
        runtime = payload.get("runtime", "onnx")
        if not isinstance(runtime, str) or not runtime.strip():
            raise ManifestError(f"model '{model_id}' runtime must be a string")
        optional = bool(payload.get("optional", False))
        models[model_id] = ModelSpec(
            model_id=model_id,
            version=version_text,
            files=tuple(parsed_files),
            sources=tuple(sources),
            runtime=runtime,
            optional=optional,
        )
    return Manifest(version=version, models=models)
