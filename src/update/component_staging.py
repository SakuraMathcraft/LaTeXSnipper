"""Prepare verified replacement payloads while preserving the active installation."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import shutil
import tempfile

from runtime.component_archive import extract_archive
from runtime.component_inventory import verify_component
from runtime.distribution_manifest import DistributionManifest, ManifestError
from runtime.installed_resources import current_target
from runtime.installation_layout import installation_manifest
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
    installed = DistributionManifest.load(installation_manifest(installed_root, current_target()[0]))
    output = output.resolve()
    cache = cache.resolve()
    if output.exists() or output.is_relative_to(installed_root) or installed_root.is_relative_to(output) or output.is_relative_to(cache) or cache.is_relative_to(output):
        raise ManifestError('Component staging must be fresh and separate from installation and cache')
    damaged = [item.name for item in installed.components if verify_component(installed_root / item.name, item)]
    damaged_bundle = False
    if target.platform == 'macos':
        from update.macos_transaction import bundle_is_damaged

        damaged_bundle = bundle_is_damaged(installed_root)
    plan = plan_component_update(installed, target, damaged_components=damaged, damaged_bundle=damaged_bundle)
    output.parent.mkdir(parents=True, exist_ok=True)
    required = sum(record.size for item in plan.downloads for record in item.files)
    if shutil.disk_usage(output.parent).free < required:
        raise OSError('Insufficient free space for replacement components')
    control = control or DownloadControl()
    with tempfile.TemporaryDirectory(prefix='component-staging-', dir=output.parent) as temporary:
        staging = Path(temporary) / 'payload'
        staging.mkdir()
        for component in plan.downloads:
            control.checkpoint()
            if status:
                status('downloading', component.name)

            def report(done: int, total: int) -> None:
                if progress:
                    progress(component.name, done, total)

            archive = download_component(component.artifact, cache, control=control, progress=report, cache_key=component.cache_key)
            control.checkpoint()
            if status:
                status('verifying', component.name)
            extract_archive(archive, staging / component.name, component=component)
        if plan.seal_required:
            seal = target.bundle_seal
            if seal is None:
                raise ManifestError('Missing signed macOS bundle resources')
            if status:
                status('downloading', 'bundle-seal')
            archive = download_component(seal.artifact, cache, control=control,
                progress=lambda done, total: progress('bundle-seal', done, total) if progress else None)
            control.checkpoint()
            if status:
                status('verifying', 'bundle-seal')
            extract_archive(archive, staging / '.bundle-seal', component=seal)
        control.checkpoint()
        manifest = staging / 'distribution.json'
        with manifest.open('w', encoding='utf-8', newline='\n') as stream:
            json.dump(target.to_dict(), stream, sort_keys=True, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        staging.rename(output)
    return plan
