"""Package immutable resources and validate the bytes handed to a release."""

from argparse import Namespace
from dataclasses import replace
from pathlib import Path
import stat
import zipfile

from desktop_distribution import build_component, write_json
from runtime.component_inventory import file_sha256, inventory_component
from runtime.distribution_manifest import Artifact, BundleSeal, Component, DistributionManifest, ManifestError, ReleaseCatalog, read_json


def artifact(path: Path, base_url: str) -> Artifact:
    return Artifact(f'{base_url}/{path.name}', file_sha256(path), path.stat().st_size)


def package_component(source: Path, output: Path, name: str, target: str, variant: str, base_url: str) -> Component:
    platform, architecture = target.split('-')
    from mathcraft_ocr.protocol import MODEL_FORMAT, WORKER_PROTOCOL

    records_before = set(output.glob(f'{name}-{platform}-{architecture}-{variant}-*.zip.json'))
    build_component(Namespace(source=source, output=output, name=name, platform=platform, architecture=architecture,
                              variant=variant, worker_protocol=0 if name == 'models' else WORKER_PROTOCOL,
                              model_format=MODEL_FORMAT, base_url=base_url))
    records = set(output.glob(f'{name}-{platform}-{architecture}-{variant}-*.zip.json'))
    changed = records - records_before
    if len(changed) != 1:
        raise ManifestError('Component packaging requires a fresh output directory')
    return Component.from_dict(read_json(changed.pop()))


def package_bundle_seal(bundle: Path, output: Path, base_url: str) -> BundleSeal:
    excluded = tuple(Path('Contents/Resources/desktop') / name for name in ('application', 'inference', 'models'))
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob('*')):
            relative = path.relative_to(bundle)
            if any(relative == prefix or relative.is_relative_to(prefix) for prefix in excluded):
                continue
            if path.is_dir() and not path.is_symlink():
                continue
            entry = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            mode = stat.S_IFLNK if path.is_symlink() else stat.S_IFREG
            entry.external_attr = (mode | stat.S_IMODE(path.lstat().st_mode)) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.readlink().as_posix().encode() if path.is_symlink() else path.read_bytes())
    files = tuple(record for record in inventory_component(bundle) if not any(Path(record.path) == prefix or Path(record.path).is_relative_to(prefix) for prefix in excluded))
    return BundleSeal(artifact(output, base_url), files)


def publish_catalog(directory: Path, version: str, output: Path) -> None:
    distributions = tuple(DistributionManifest.load(path) for path in sorted(directory.glob('distribution-*.json')))
    catalog = ReleaseCatalog(version, distributions)
    expected = {('windows', 'x86_64', 'cpu'), ('windows', 'x86_64', 'gpu'),
                ('linux', 'x86_64', 'cpu'), ('linux', 'x86_64', 'gpu'), ('macos', 'arm64', 'cpu')}
    if {item.target for item in distributions} != expected:
        raise ManifestError('Release does not contain all five declared desktop distributions')
    for distribution in distributions:
        resources = [component.artifact for component in distribution.components]
        resources.append(distribution.installer)
        if distribution.bundle_seal:
            resources.append(distribution.bundle_seal.artifact)
        for resource in resources:
            if resource is None:
                raise ManifestError('Release is missing a required artifact')
            from urllib.parse import urlsplit, unquote

            path = directory / unquote(urlsplit(resource.url).path.rsplit('/', 1)[-1])
            if not path.is_file() or path.stat().st_size != resource.size or file_sha256(path) != resource.sha256:
                raise ManifestError(f'Release payload failed final verification: {path.name}')
    write_json(output, catalog.to_dict())
    checksums = {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file() and path.suffix != '.json'}
    (directory / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(checksums.items())), encoding='utf-8')


def finalize_windows(directory: Path, signed: Path) -> None:
    for path in directory.glob('distribution-windows-*.json'):
        distribution = DistributionManifest.load(path)
        filename = f'LaTeXSnipper_{distribution.version}_windows_x86_64_{distribution.edition}.exe'
        source = signed / filename
        if not source.is_file():
            raise ManifestError(f'Missing signed Windows installer: {filename}')
        import shutil

        shutil.copy2(source, directory / filename)
        base_url = distribution.component('application').artifact.url.rsplit('/', 1)[0]
        distribution = replace(distribution, installer=artifact(directory / filename, base_url))
        write_json(path, distribution.to_dict())
