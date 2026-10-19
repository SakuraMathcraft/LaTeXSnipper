"""Select the business payload only when its fixed base matches."""

from dataclasses import dataclass

from runtime.distribution_manifest import Component, DistributionManifest, ManifestError


@dataclass(frozen=True)
class ComponentUpdatePlan:
    target: DistributionManifest
    downloads: tuple[Component, ...]
    installer_required: bool = False

    @property
    def download_bytes(self) -> int:
        return sum(item.artifact.size for item in self.downloads)


def plan_component_update(
    installed: DistributionManifest, target: DistributionManifest
) -> ComponentUpdatePlan:
    if installed.target != target.target:
        raise ManifestError(
            "An update cannot change platform, architecture or installed edition"
        )
    if tuple(map(int, target.version.split("."))) < tuple(
        map(int, installed.version.split("."))
    ):
        raise ManifestError("A normal update cannot downgrade the product")
    if installed.base_id != target.base_id:
        return ComponentUpdatePlan(target, (), installer_required=True)
    changed = installed.application.content_sha256 != target.application.content_sha256
    return ComponentUpdatePlan(target, (target.application,) if changed else ())
