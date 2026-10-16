"""Strict component identities shared by installers, builds and updates."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

_COMPONENTS = frozenset({'application', 'inference', 'models'})
_PLATFORMS = frozenset({'windows', 'linux', 'macos'})
_ARCHITECTURES = frozenset({'x86_64', 'arm64'})
_DIGEST = re.compile(r'[0-9a-f]{64}')
_VERSION = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')


class ManifestError(ValueError):
    """An invalid identity or unsupported distribution protocol."""


def _fields(value: object, keys: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ManifestError(f'Expected exactly these fields: {sorted(keys)}')
    return value


def _choice(value: object, choices: frozenset[str], label: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ManifestError(f'Invalid {label}: {value!r}')
    return value


def _positive(value: object, label: str, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ManifestError(f'Invalid {label}: {value!r}')
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise ManifestError('Expected a lowercase SHA256 digest')
    return value


def safe_relative_path(value: object) -> str:
    """Accept portable relative resource names without traversal or aliases."""
    if not isinstance(value, str) or not value or any(ord(c) < 32 for c in value):
        raise ManifestError('Invalid resource path')
    parts = value.split('/')
    if '\\' in value or ':' in value or any(p in {'', '.', '..'} or p.endswith((' ', '.')) for p in parts):
        raise ManifestError(f'Unsafe resource path: {value!r}')
    if any(p.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))} or any(c in p for c in '<>"|?*') for p in parts):
        raise ManifestError(f'Nonportable resource path: {value!r}')
    return value


def _link_target(path: str, target: object) -> str:
    if not isinstance(target, str) or not target or target.startswith('/'):
        raise ManifestError('A symlink must have a relative target')
    if '\\' in target or ':' in target or any(ord(c) < 32 for c in target):
        raise ManifestError('Invalid symlink target')
    stack = list(PurePosixPath(path).parent.parts)
    for part in target.split('/'):
        if part == '..':
            if not stack:
                raise ManifestError('Symlink escapes its component')
            stack.pop()
        elif part not in {'', '.'}:
            stack.append(part)
    return target


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ManifestError(f'Duplicate JSON field: {key}')
        result[key] = value
    return result


def read_json(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ManifestError('Expected a JSON object')
    return value


@dataclass(frozen=True)
class Artifact:
    url: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        if not isinstance(self.url, str):
            raise ManifestError('Artifact URL must be a string')
        parsed = urlsplit(self.url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ManifestError('Artifact URL must use HTTPS without credentials or fragment')
        _digest(self.sha256)
        _positive(self.size, 'artifact size')

    @classmethod
    def from_dict(cls, value: object) -> Artifact:
        data = _fields(value, {'url', 'sha256', 'size'})
        return cls(**data)

    def to_dict(self) -> dict:
        return {'url': self.url, 'sha256': self.sha256, 'size': self.size}


@dataclass(frozen=True)
class FileRecord:
    path: str
    sha256: str
    size: int
    mode: int
    kind: str = 'file'
    target: str = ''

    def __post_init__(self) -> None:
        safe_relative_path(self.path)
        _digest(self.sha256)
        _positive(self.size, 'file size', allow_zero=True)
        if type(self.mode) is not int or not 0 <= self.mode <= 0o777:
            raise ManifestError('Invalid file permissions')
        _choice(self.kind, frozenset({'file', 'symlink'}), 'file kind')
        if self.kind == 'symlink':
            encoded = _link_target(self.path, self.target).encode('utf-8')
            if self.size != len(encoded) or self.sha256 != hashlib.sha256(encoded).hexdigest():
                raise ManifestError('Symlink identity does not match its target')
        elif self.target != '':
            raise ManifestError('A regular file cannot declare a link target')

    @classmethod
    def from_dict(cls, value: object) -> FileRecord:
        data = _fields(value, {'path', 'sha256', 'size', 'mode', 'kind', 'target'})
        return cls(**data)

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in ('path', 'sha256', 'size', 'mode', 'kind', 'target')}


@dataclass(frozen=True)
class Component:
    name: str
    platform: str
    architecture: str
    variant: str
    worker_protocol: int
    model_format: int
    files: tuple[FileRecord, ...]
    artifact: Artifact

    def __post_init__(self) -> None:
        _choice(self.name, _COMPONENTS, 'component')
        shared = self.name == 'models'
        _choice(self.platform, _PLATFORMS | (frozenset({'any'}) if shared else frozenset()), 'platform')
        _choice(self.architecture, _ARCHITECTURES | (frozenset({'any'}) if shared else frozenset()), 'architecture')
        variants = frozenset({'cpu', 'gpu'}) if self.name == 'inference' else frozenset({'common'})
        _choice(self.variant, variants, 'variant')
        if self.platform == 'macos' and self.variant == 'gpu':
            raise ManifestError('macOS has no CUDA GPU distribution')
        _positive(self.worker_protocol, 'worker protocol', allow_zero=shared)
        if shared and self.worker_protocol != 0:
            raise ManifestError('Models do not participate in the worker protocol')
        _positive(self.model_format, 'model format')
        validate_inventory(self.files)
        if not isinstance(self.artifact, Artifact):
            raise ManifestError('Invalid artifact')

    @property
    def content_sha256(self) -> str:
        identity = {
            'name': self.name, 'platform': self.platform, 'architecture': self.architecture,
            'variant': self.variant, 'worker_protocol': self.worker_protocol, 'model_format': self.model_format,
            'files': [record.to_dict() for record in sorted(self.files, key=lambda item: item.path)],
        }
        return hashlib.sha256(canonical_json(identity)).hexdigest()

    @property
    def cache_key(self) -> str:
        return f'{self.platform}-{self.architecture}-{self.variant}-{self.name}-{self.artifact.sha256}'

    @classmethod
    def from_dict(cls, value: object) -> Component:
        keys = {'name', 'platform', 'architecture', 'variant', 'worker_protocol', 'model_format', 'files', 'artifact', 'content_sha256'}
        data = dict(_fields(value, keys))
        claimed_digest = _digest(data.pop('content_sha256'))
        if not isinstance(data['files'], list):
            raise ManifestError('Inventory must be an array')
        data['files'] = tuple(FileRecord.from_dict(item) for item in data['files'])
        data['artifact'] = Artifact.from_dict(data['artifact'])
        result = cls(**data)
        if result.content_sha256 != claimed_digest:
            raise ManifestError('Component identity does not match its inventory')
        return result

    def to_dict(self) -> dict:
        result = {name: getattr(self, name) for name in ('name', 'platform', 'architecture', 'variant', 'worker_protocol', 'model_format')}
        result.update(files=[item.to_dict() for item in sorted(self.files, key=lambda item: item.path)], artifact=self.artifact.to_dict(), content_sha256=self.content_sha256)
        return result


def validate_inventory(files: tuple[FileRecord, ...]) -> None:
    if not isinstance(files, tuple) or not files or not all(isinstance(item, FileRecord) for item in files):
        raise ManifestError('A resource needs an immutable, non-empty inventory')
    seen = set()
    for item in files:
        key = item.path.casefold()
        if key in seen:
            raise ManifestError(f'Duplicate resource path: {item.path}')
        seen.add(key)
    for item in files:
        parent = PurePosixPath(item.path).parent
        if any(str(part).casefold() in seen for part in parent.parents) or str(parent).casefold() in seen:
            raise ManifestError(f'A resource cannot be the parent of another resource: {item.path}')


@dataclass(frozen=True)
class BundleSeal:
    artifact: Artifact
    files: tuple[FileRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, Artifact):
            raise ManifestError('Invalid bundle-seal artifact')
        validate_inventory(self.files)
        components = tuple(PurePosixPath('Contents/Resources/desktop') / name for name in _COMPONENTS)
        for record in self.files:
            path = PurePosixPath(record.path)
            if path.parts[0] != 'Contents' or any(path == prefix or path.is_relative_to(prefix) for prefix in components):
                raise ManifestError('Bundle seal must contain only outer Contents resources')

    @classmethod
    def from_dict(cls, value: object) -> BundleSeal:
        data = _fields(value, {'artifact', 'files'})
        if not isinstance(data['files'], list):
            raise ManifestError('Bundle-seal inventory must be an array')
        return cls(Artifact.from_dict(data['artifact']), tuple(FileRecord.from_dict(item) for item in data['files']))

    def to_dict(self) -> dict:
        return {'artifact': self.artifact.to_dict(), 'files': [record.to_dict() for record in sorted(self.files, key=lambda item: item.path)]}


@dataclass(frozen=True)
class DistributionManifest:
    version: str
    platform: str
    architecture: str
    edition: str
    components: tuple[Component, ...]
    installer: Artifact | None = None
    release_tag: str = ''
    bundle_seal: BundleSeal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not _VERSION.fullmatch(self.version):
            raise ManifestError('Expected a stable product version without a v prefix')
        if not self.release_tag:
            object.__setattr__(self, 'release_tag', f'v{self.version}')
        if self.release_tag not in {f'v{self.version}', f'v{self.version}-LTS'}:
            raise ManifestError('Release tag does not match the product version')
        if self.installer is not None and not isinstance(self.installer, Artifact):
            raise ManifestError('Invalid first-install artifact')
        if self.bundle_seal is not None and (self.platform != 'macos' or not isinstance(self.bundle_seal, BundleSeal)):
            raise ManifestError('Only macOS distributions declare bundle-seal resources')
        _choice(self.platform, _PLATFORMS, 'platform')
        _choice(self.architecture, _ARCHITECTURES, 'architecture')
        _choice(self.edition, frozenset({'cpu', 'gpu'}), 'edition')
        if self.platform == 'macos' and self.edition == 'gpu':
            raise ManifestError('macOS has no CUDA GPU distribution')
        if not isinstance(self.components, tuple) or not all(isinstance(item, Component) for item in self.components):
            raise ManifestError('Invalid components')
        if len(self.components) != 3 or {item.name for item in self.components} != _COMPONENTS:
            raise ManifestError('Exactly one application, inference and models component is required')
        for item in self.components:
            if item.platform not in {self.platform, 'any'} or item.architecture not in {self.architecture, 'any'}:
                raise ManifestError(f'Component target mismatch: {item.name}')
            if item.name == 'inference' and item.variant != self.edition:
                raise ManifestError('Inference component does not match the installed edition')
        if len({item.worker_protocol for item in self.components if item.name != 'models'}) != 1:
            raise ManifestError('Worker protocol mismatch')
        if len({item.model_format for item in self.components}) != 1:
            raise ManifestError('Model format mismatch')

    @property
    def target(self) -> tuple[str, str, str]:
        return self.platform, self.architecture, self.edition

    def component(self, name: str) -> Component:
        _choice(name, _COMPONENTS, 'component')
        return next(item for item in self.components if item.name == name)

    @classmethod
    def from_dict(cls, value: object) -> DistributionManifest:
        keys = {'schema', 'product', 'version', 'platform', 'architecture', 'edition', 'components', 'installer', 'release_tag', 'bundle_seal'}
        data = dict(_fields(value, keys))
        schema = data.pop('schema')
        if type(schema) is not int or schema != 1:
            raise ManifestError('Unsupported distribution schema')
        if data.pop('product') != 'latexsnipper':
            raise ManifestError('Unexpected product')
        if not isinstance(data['components'], list):
            raise ManifestError('Components must be an array')
        data['components'] = tuple(Component.from_dict(item) for item in data['components'])
        if data['installer'] is not None:
            data['installer'] = Artifact.from_dict(data['installer'])
        if data['bundle_seal'] is not None:
            data['bundle_seal'] = BundleSeal.from_dict(data['bundle_seal'])
        return cls(**data)

    @classmethod
    def load(cls, path: Path) -> DistributionManifest:
        return cls.from_dict(read_json(path))

    def to_dict(self) -> dict:
        return {
            'schema': 1, 'product': 'latexsnipper', 'version': self.version,
            'platform': self.platform, 'architecture': self.architecture, 'edition': self.edition,
            'components': [self.component(name).to_dict() for name in sorted(_COMPONENTS)],
            'installer': self.installer.to_dict() if self.installer else None,
            'release_tag': self.release_tag,
            'bundle_seal': self.bundle_seal.to_dict() if self.bundle_seal else None,
        }

    def installed_identity(self) -> DistributionManifest:
        """Carrier digests cannot be embedded in the very carrier they identify."""
        return replace(self, installer=None, bundle_seal=None)


@dataclass(frozen=True)
class ReleaseCatalog:
    version: str
    distributions: tuple[DistributionManifest, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not _VERSION.fullmatch(self.version):
            raise ManifestError('Invalid release version')
        if not isinstance(self.distributions, tuple) or not self.distributions:
            raise ManifestError('A release needs distributions')
        seen = set()
        for item in self.distributions:
            if not isinstance(item, DistributionManifest) or item.version != self.version:
                raise ManifestError('Release distribution version mismatch')
            if item.installer is None:
                raise ManifestError('A published distribution needs a first-install artifact')
            if item.platform == 'macos' and item.bundle_seal is None:
                raise ManifestError('A macOS release needs its signed bundle-seal payload')
            if item.target in seen:
                raise ManifestError('Duplicate release target')
            seen.add(item.target)

    def select(self, platform: str, architecture: str, edition: str) -> DistributionManifest:
        target = platform, architecture, edition
        matches = [item for item in self.distributions if item.target == target]
        if not matches:
            raise ManifestError(f'No release distribution for {target}')
        return matches[0]

    @classmethod
    def from_dict(cls, value: object) -> ReleaseCatalog:
        data = _fields(value, {'schema', 'product', 'version', 'distributions'})
        if type(data['schema']) is not int or data['schema'] != 1 or data['product'] != 'latexsnipper':
            raise ManifestError('Unsupported release catalog')
        if not isinstance(data['distributions'], list):
            raise ManifestError('Distributions must be an array')
        return cls(data['version'], tuple(DistributionManifest.from_dict(item) for item in data['distributions']))

    @classmethod
    def load(cls, path: Path) -> ReleaseCatalog:
        return cls.from_dict(read_json(path))

    def to_dict(self) -> dict:
        return {'schema': 1, 'product': 'latexsnipper', 'version': self.version,
                'distributions': [item.to_dict() for item in sorted(self.distributions, key=lambda item: item.target)]}
