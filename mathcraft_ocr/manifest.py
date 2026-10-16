# coding: utf-8

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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

    @property
    def content_sha256(self) -> str:
        identity = {'model_id': self.model_id, 'version': self.version, 'runtime': self.runtime,
                    'files': sorted((item.path, item.sha256) for item in self.files)}
        return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


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


def model_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or any(ord(c) < 32 for c in value):
        raise ManifestError('invalid model resource path')
    if any(part in {'', '.', '..'} or part.endswith((' ', '.')) for part in value.split('/')):
        raise ManifestError('unsafe model resource path')
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f'duplicate manifest field: {key}')
        result[key] = value
    return result


def load_manifest(path: str | Path | None = None) -> Manifest:
    manifest_path = Path(path) if path else _manifest_path()
    raw = json.loads(manifest_path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)
    raw = _require_dict(raw, "root")
    if set(raw) != {'version', 'models'}:
        raise ManifestError('unexpected model manifest fields')
    version = raw.get("version")
    if type(version) is not int or version != 1:
        raise ManifestError("unsupported model manifest format")
    raw_models = _require_dict(raw.get("models"), "models")
    if not raw_models:
        raise ManifestError('model manifest must not be empty')
    models: dict[str, ModelSpec] = {}
    for model_id, payload in raw_models.items():
        payload = _require_dict(payload, model_id)
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', model_id):
            raise ManifestError('invalid model id')
        if not {'version', 'runtime', 'files', 'sources'} <= set(payload) or set(payload) - {'version', 'runtime', 'files', 'sources', 'optional'}:
            raise ManifestError('unexpected model fields')
        files = payload.get("files")
        if not isinstance(files, list) or not files:
            raise ManifestError(f"model '{model_id}' must define non-empty files")
        parsed_files: list[ModelFileSpec] = []
        seen = set()
        for item in files:
            item = _require_dict(item, f"{model_id}.files")
            if set(item) != {'path', 'sha256'}:
                raise ManifestError('unexpected model file fields')
            model_path = item.get("path")
            model_relative_path(model_path)
            if model_path.casefold() in seen:
                raise ManifestError('duplicate model file')
            seen.add(model_path.casefold())
            sha256 = item.get('sha256')
            if not isinstance(sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', sha256):
                raise ManifestError('model file needs a SHA256 digest')
            parsed_files.append(ModelFileSpec(path=model_path, sha256=sha256))
        sources = payload['sources']
        if not isinstance(sources, list) or not sources or not all(isinstance(s, str) and urlsplit(s).scheme == 'https' and urlsplit(s).hostname and not urlsplit(s).username and not urlsplit(s).password and not urlsplit(s).fragment for s in sources):
            raise ManifestError(f"model '{model_id}' sources must be a list[str]")
        version_text = payload['version']
        if not isinstance(version_text, str) or not version_text:
            raise ManifestError(f"model '{model_id}' version must be a string")
        runtime = payload['runtime']
        if runtime != 'onnx':
            raise ManifestError(f"model '{model_id}' runtime must be a string")
        optional = payload.get('optional', False)
        if type(optional) is not bool:
            raise ManifestError('model optional flag must be boolean')
        models[model_id] = ModelSpec(
            model_id=model_id,
            version=version_text,
            files=tuple(parsed_files),
            sources=tuple(sources),
            runtime=runtime,
            optional=optional,
        )
    return Manifest(version=version, models=models)
