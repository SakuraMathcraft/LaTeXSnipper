"""Prepare verified replacement payloads while preserving the active installation."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from runtime.component_archive import extract_archive
from runtime.distribution_manifest import DistributionManifest, ManifestError
from runtime.installation_layout import installation_manifest
from runtime.installed_resources import current_target
from update.component_download import DownloadControl, download_component
from update.component_plan import ComponentUpdatePlan, plan_component_update


def prepare_components(
    installed_root: Path,
    target: DistributionManifest,
    output: Path,
    cache: Path,
    *,
    control: DownloadControl | None = None,
    progress: Callable[[str, int, int], None] | None = None,
    status: Callable[[str, str], None] | None = None,
) -> ComponentUpdatePlan:
    installed_root = installed_root.resolve()
    installed = DistributionManifest.load(
        installation_manifest(installed_root, current_target()[0])
    )
    output = output.resolve()
    cache = cache.resolve()
    if (
        output.exists()
        or output.is_relative_to(installed_root)
        or installed_root.is_relative_to(output)
        or output.is_relative_to(cache)
        or cache.is_relative_to(output)
    ):
        raise ManifestError(
            "Component staging must be fresh and separate from installation and cache"
        )
    plan = plan_component_update(installed, target)
    if plan.installer_required:
        raise ManifestError(
            "Fixed base changed; install the complete desktop installer"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    required = sum(record.size for item in plan.downloads for record in item.files)
    if shutil.disk_usage(output.parent).free < required:
        raise OSError("Insufficient free space for replacement components")
    control = control or DownloadControl()
    with tempfile.TemporaryDirectory(
        prefix="component-staging-", dir=output.parent
    ) as temporary:
        staging = Path(temporary) / "payload"
        staging.mkdir()
        for component in plan.downloads:
            control.checkpoint()
            if status:
                status("downloading", component.name)

            def report(done: int, total: int, name: str = component.name) -> None:
                if progress:
                    progress(name, done, total)

            archive = download_component(
                component.artifact,
                cache,
                control=control,
                progress=report,
                cache_key=component.cache_key,
            )
            control.checkpoint()
            if status:
                status("verifying", component.name)
            extract_archive(archive, staging / component.name, component=component)
        control.checkpoint()
        manifest = staging / "distribution.json"
        with manifest.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(target.to_dict(), stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        staging.rename(output)
    return plan
