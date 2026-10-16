"""Plan complete component replacements without patch chains or filename guessing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from runtime.distribution_manifest import Component, DistributionManifest, ManifestError


@dataclass(frozen=True)
class ComponentUpdatePlan:
    target: DistributionManifest
    downloads: tuple[Component, ...]
    seal_required: bool = False

    @property
    def download_bytes(self) -> int:
        seal = self.target.bundle_seal.artifact.size if self.seal_required and self.target.bundle_seal else 0
        return sum(item.artifact.size for item in self.downloads) + seal


def plan_component_update(
    installed: DistributionManifest,
    target: DistributionManifest,
    *,
    damaged_components: Iterable[str] = (),
    damaged_bundle: bool = False,
) -> ComponentUpdatePlan:
    """Keep the installed edition and select all changed or damaged target components."""
    if installed.target != target.target:
        raise ManifestError('An update cannot change platform, architecture or installed edition')
    current_version = tuple(int(part) for part in installed.version.split('.'))
    target_version = tuple(int(part) for part in target.version.split('.'))
    if target_version < current_version:
        raise ManifestError('A normal update cannot downgrade the product')
    damaged = frozenset(damaged_components)
    if not damaged <= {item.name for item in installed.components}:
        raise ManifestError('Unknown damaged component')
    downloads = tuple(
        item for item in target.components
        if item.name in damaged or installed.component(item.name).content_sha256 != item.content_sha256
    )
    seal_required = target.platform == 'macos' and (bool(downloads) or target.version != installed.version or damaged_bundle)
    if seal_required and target.bundle_seal is None:
        raise ManifestError('A macOS update requires a signed bundle-seal payload')
    return ComponentUpdatePlan(target, downloads, seal_required)
