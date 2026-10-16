"""Build and inspect the component protocol used by desktop distribution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import sys
from urllib.parse import quote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]

from distribution_inputs import load_sources, load_dependencies, load_resources  # noqa: E402
from runtime.component_inventory import file_sha256, inventory_component, verify_component  # noqa: E402
from runtime.distribution_manifest import Artifact, Component, DistributionManifest, ManifestError, ReleaseCatalog, read_json  # noqa: E402
from update.component_plan import plan_component_update  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def build_component(args: argparse.Namespace) -> None:
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output == source or output.is_relative_to(source):
        raise ManifestError('Output must be outside the component source')
    records = inventory_component(source)
    output.mkdir(parents=True, exist_ok=True)
    placeholder = Artifact(args.base_url.rstrip('/') + '/pending.zip', '0' * 64, 1)
    component = Component(args.name, args.platform, args.architecture, args.variant, args.worker_protocol, args.model_format, records, placeholder)
    filename = f'{component.name}-{component.platform}-{component.architecture}-{component.variant}-{component.content_sha256}.zip'
    archive = output / filename
    try:
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for record in records:
                entry = zipfile.ZipInfo(record.path, date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = ((stat.S_IFLNK if record.kind == 'symlink' else stat.S_IFREG) | record.mode) << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                if record.kind == 'symlink':
                    package.writestr(entry, record.target.encode('utf-8'))
                else:
                    with source.joinpath(*record.path.split('/')).open('rb') as incoming, package.open(entry, 'w', force_zip64=True) as outgoing:
                        for block in iter(lambda: incoming.read(1024 * 1024), b''):
                            outgoing.write(block)
        if verify_component(source, component):
            raise ManifestError('Component source changed during packaging')
        artifact = Artifact(args.base_url.rstrip('/') + '/' + quote(filename), file_sha256(archive), archive.stat().st_size)
        component = Component(args.name, args.platform, args.architecture, args.variant, args.worker_protocol, args.model_format, records, artifact)
        metadata = output / f'{filename}.json'
        write_json(metadata, component.to_dict())
        print(json.dumps({'metadata': str(metadata), 'uncompressed_bytes': sum(item.size for item in records), 'download_bytes': artifact.size}))
    except Exception:
        archive.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    sources = commands.add_parser('sources', help='Validate pinned source archives without downloading them')
    sources.add_argument('--catalog', type=Path, default=ROOT / 'packaging/runtime/sources.lock.json')
    sources.add_argument('--dependency-lock', type=Path, default=ROOT / 'packaging/runtime/dependencies.lock.json')
    sources.add_argument('--resource-lock', type=Path, default=ROOT / 'packaging/runtime/resources.lock.json')
    component = commands.add_parser('component', help='Package an immutable component and inventory')
    component.add_argument('--source', type=Path, required=True)
    component.add_argument('--output', type=Path, required=True)
    component.add_argument('--name', choices=('application', 'inference', 'models'), required=True)
    component.add_argument('--platform', choices=('windows', 'linux', 'macos', 'any'), required=True)
    component.add_argument('--architecture', choices=('x86_64', 'arm64', 'any'), required=True)
    component.add_argument('--variant', choices=('common', 'cpu', 'gpu'), required=True)
    component.add_argument('--worker-protocol', type=int, required=True)
    component.add_argument('--model-format', type=int, required=True)
    component.add_argument('--base-url', required=True)
    manifest = commands.add_parser('manifest', help='Assemble a target distribution from component metadata')
    manifest.add_argument('--version', required=True)
    manifest.add_argument('--platform', required=True)
    manifest.add_argument('--architecture', required=True)
    manifest.add_argument('--edition', required=True)
    manifest.add_argument('--release-tag', default='')
    manifest.add_argument('--component', type=Path, action='append', required=True)
    manifest.add_argument('--output', type=Path, required=True)
    manifest.add_argument('--installer-url')
    manifest.add_argument('--installer-sha256')
    manifest.add_argument('--installer-size', type=int)
    catalog = commands.add_parser('catalog', help='Validate and publish all explicitly declared release targets')
    catalog.add_argument('--version', required=True)
    catalog.add_argument('--distribution', type=Path, action='append', required=True)
    catalog.add_argument('--output', type=Path, required=True)
    plan = commands.add_parser('plan', help='Inspect an update or repair plan')
    plan.add_argument('--installed', type=Path, required=True)
    plan.add_argument('--target', type=Path, required=True)
    plan.add_argument('--damaged', action='append', default=[])
    fetch = commands.add_parser('fetch', help='Fetch a catalog through authoritative GitHub metadata')
    fetch.add_argument('--cache', type=Path, required=True)
    fetch.add_argument('--output', type=Path, required=True)
    prepare = commands.add_parser('prepare', help='Prepare verified replacements without changing an installation')
    prepare.add_argument('--installed-root', type=Path, required=True)
    prepare.add_argument('--target', type=Path, required=True)
    prepare.add_argument('--cache', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'sources':
        source_lock = load_sources(args.catalog)
        dependency_lock = load_dependencies(args.dependency_lock, source_lock)
        resource_lock = load_resources(args.resource_lock)
        print(json.dumps({'targets': sorted(source_lock['targets']), 'dependencies': {target: len(items) for target, items in dependency_lock['targets'].items()}, 'models': sorted(resource_lock['models']), 'pandoc': resource_lock['pandoc_version']}))
    elif args.command == 'component':
        build_component(args)
    elif args.command == 'manifest':
        components = tuple(Component.from_dict(read_json(path)) for path in args.component)
        installer = None
        if any(value is not None for value in (args.installer_url, args.installer_sha256, args.installer_size)):
            installer = Artifact(args.installer_url, args.installer_sha256, args.installer_size)
        distribution = DistributionManifest(args.version, args.platform, args.architecture, args.edition, components, installer, args.release_tag)
        write_json(args.output, distribution.to_dict())
    elif args.command == 'catalog':
        release = ReleaseCatalog(args.version, tuple(DistributionManifest.load(path) for path in args.distribution))
        write_json(args.output, release.to_dict())
    elif args.command == 'fetch':
        from update.component_release import fetch_component_release

        release = fetch_component_release(args.cache)
        write_json(args.output, release.catalog.to_dict())
    elif args.command == 'prepare':
        from update.component_staging import prepare_components

        update = prepare_components(args.installed_root, DistributionManifest.load(args.target), args.output, args.cache)
        print(json.dumps({'downloads': [item.cache_key for item in update.downloads], 'download_bytes': update.download_bytes}))
    else:
        installed = DistributionManifest.load(args.installed)
        target = DistributionManifest.load(args.target)
        update = plan_component_update(installed, target, damaged_components=args.damaged)
        print(json.dumps({'downloads': [item.cache_key for item in update.downloads], 'download_bytes': update.download_bytes}))


if __name__ == '__main__':
    main()
