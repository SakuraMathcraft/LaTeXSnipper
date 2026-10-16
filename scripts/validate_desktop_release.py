"""Validate actual native installers and hardware-backed recognition in release CI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]

from mathcraft_ocr.protocol import validate_response  # noqa: E402
from runtime.component_archive import extract_archive  # noqa: E402
from runtime.component_inventory import verify_component  # noqa: E402
from runtime.distribution_manifest import DistributionManifest, ManifestError  # noqa: E402
from runtime.installed_resources import InstalledResources, current_target, worker_command, worker_environment  # noqa: E402
from runtime.installation_layout import installation_manifest, macos_bundle  # noqa: E402
from runtime.processes import hidden_subprocess_kwargs  # noqa: E402
from update.component_plan import plan_component_update  # noqa: E402
from update.deployment_transaction import atomic_json, verify_distribution  # noqa: E402
from update.deployment_validation import validate_installed_worker  # noqa: E402
from update.platform_deployment import deployment_transaction  # noqa: E402


def archive_path(directory: Path, url: str) -> Path:
    from urllib.parse import urlsplit, unquote

    return directory / unquote(urlsplit(url).path.rsplit('/', 1)[-1])


def validate_recognition(root: Path, manifest: DistributionManifest, output: Path) -> dict:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new('RGB', (720, 170), 'white')
    ImageDraw.Draw(image).text((30, 40), '1 + 1 = 2', fill='black', font=ImageFont.load_default(size=64))
    sample = output / 'recognition.png'
    image.save(sample)
    resources = InstalledResources(root, manifest)
    requests = [{'protocol': manifest.component('application').worker_protocol, 'id': action, 'action': action, 'image': str(sample)}
                for action in ('recognize_formula', 'recognize_text', 'recognize_mixed')]
    result = subprocess.run(worker_command(resources), input=''.join(json.dumps(item) + '\n' for item in requests),
                            capture_output=True, text=True, encoding='utf-8', timeout=600,
                            env=worker_environment(resources), **hidden_subprocess_kwargs())
    if result.returncode:
        raise ManifestError(f'Release recognition worker failed: {result.stderr[-4000:]}')
    lines = result.stdout.splitlines()
    if len(lines) != len(requests):
        raise ManifestError('Recognition validation received an incomplete worker protocol')
    reports = {}
    provider = 'CUDAExecutionProvider' if manifest.edition == 'gpu' else 'CPUExecutionProvider'
    for request, line in zip(requests, lines):
        response = validate_response(json.loads(line), request['id'])
        if not response['ok']:
            raise ManifestError(f'Release recognition failed: {response.get("error")}')
        report = response['result']
        if not report.get('text', '').strip() or report.get('provider') != provider:
            raise ManifestError('Recognition did not produce text on the required execution provider')
        if manifest.edition == 'gpu':
            native = report.get('native_modules', {})
            if not native or any(not Path(path).resolve().is_relative_to(root / 'inference/native') for path in native.values()):
                raise ManifestError('CUDA recognition did not use the complete private native runtime')
        reports[request['action']] = report
    return reports


def prepare_repair(directory: Path, root: Path, target: DistributionManifest, staged: Path) -> None:
    installed = DistributionManifest.load(installation_manifest(root, target.platform))
    damaged = [component.name for component in installed.components if verify_component(root / component.name, component)]
    plan = plan_component_update(installed, target, damaged_components=damaged, damaged_bundle=target.platform == 'macos')
    staged.mkdir()
    atomic_json(staged / 'distribution.json', target.to_dict())
    for component in plan.downloads:
        extract_archive(archive_path(directory, component.artifact.url), staged / component.name, component=component)
    if plan.seal_required:
        seal = target.bundle_seal
        if seal is None:
            raise ManifestError('Missing macOS repair seal')
        extract_archive(archive_path(directory, seal.artifact.url), staged / '.bundle-seal', component=seal)


def native_install(directory: Path, target: DistributionManifest, work: Path) -> Path:
    if target.installer is None:
        raise ManifestError('A native acceptance run requires a first-install carrier')
    carrier = archive_path(directory, target.installer.url)
    if target.platform == 'windows':
        root = work / 'installed'
        subprocess.run([str(carrier), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', f'/DIR={root}'], check=True, timeout=1800)
        return root
    if target.platform == 'linux':
        extracted = work / f'installer-{target.edition}'
        extract_archive(carrier, extracted)
        subprocess.run(['sudo', 'sh', str(extracted / 'LaTeXSnipper/install.sh')], check=True, timeout=1800)
        return Path('/usr/lib/latexsnipper')
    mount = work / 'volume'
    mount.mkdir()
    subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount), str(carrier)], check=True, timeout=120)
    bundle = work / 'LaTeXSnipper.app'
    try:
        subprocess.run(['ditto', str(mount / 'LaTeXSnipper.app'), str(bundle)], check=True, timeout=900)
    finally:
        subprocess.run(['hdiutil', 'detach', str(mount)], check=True, timeout=120)
    from update.macos_transaction import verify_bundle

    verify_bundle(bundle)
    return bundle / 'Contents/Resources/desktop'


def native_acceptance(directory: Path, work: Path, targets: list[DistributionManifest]) -> dict:
    reports = {}
    root = None
    try:
        for target in targets:
            root = native_install(directory, target, work)
            installed = DistributionManifest.load(installation_manifest(root, target.platform))
            if installed != target.installed_identity():
                raise ManifestError('Native first-install identity differs from the published component combination')
            verify_distribution(root, target)
            validate_installed_worker(root, target)
            retained = (root / 'inference/runtime.json').read_bytes()
            # Damage one model file and prove repair replaces only its owning
            # component, rather than silently downloading a different version.
            record = min((item for item in target.component('models').files if item.kind == 'file'), key=lambda item: item.size)
            (root / 'models' / record.path).write_bytes(b'injected acceptance damage')
            staged = work / f'repair-{target.edition}'
            prepare_repair(directory, root, target, staged)
            transaction = deployment_transaction(root)
            transaction.apply(staged, validate=validate_installed_worker)
            verify_distribution(root, target)
            if (root / 'inference/runtime.json').read_bytes() != retained:
                raise ManifestError('Repair unexpectedly changed the inference component')
            report = {'first_install': True, 'same_version_model_repair': True}
            if target.edition == 'cpu':
                report['recognition'] = validate_recognition(root, target, work)
            reports[target.edition] = report
    finally:
        if root is not None:
            system = targets[0].platform
            if system == 'windows':
                uninstaller = root / 'unins000.exe'
                if not uninstaller.is_file():
                    raise ManifestError('Installed Windows release has no uninstaller')
                subprocess.run([str(uninstaller), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], check=True, timeout=900)
            elif system == 'linux':
                subprocess.run(['sudo', 'dpkg', '--purge', 'latexsnipper-inference', 'latexsnipper-models', 'latexsnipper'], check=True, timeout=900)
            else:
                shutil.rmtree(macos_bundle(root))
            remaining = [name for name in ('application', 'inference', 'models') if (root / name).exists()]
            if remaining or installation_manifest(root, system).exists():
                raise ManifestError(f'Uninstall left owned installation resources: {remaining}')
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gpu', action='store_true')
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ManifestError('Native installer acceptance must run in GitHub Actions')
    directory = args.directory.resolve(strict=True)
    system, architecture = current_target()
    if system == 'linux' and not args.gpu and os.geteuid() != 0:
        subprocess.run(['sudo', 'env', 'GITHUB_ACTIONS=true', sys.executable, str(Path(__file__).resolve()),
                        '--directory', str(directory), '--output', str(args.output.resolve())], check=True)
        return
    targets = [DistributionManifest.load(path) for path in sorted(directory.glob(f'distribution-{system}-{architecture}-*.json'))]
    if not targets:
        raise ManifestError('No matching native release targets')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='release-acceptance-') as temporary:
        work = Path(temporary)
        if args.gpu:
            target, = (item for item in targets if item.edition == 'gpu')
            root = work / 'components'
            root.mkdir()
            for component in target.components:
                extract_archive(archive_path(directory, component.artifact.url), root / component.name, component=component)
            verify_distribution(root, target)
            validate_installed_worker(root, target)
            result = {'gpu_hardware_validated': True, 'recognition': validate_recognition(root, target, work)}
        else:
            result = native_acceptance(directory, work, targets)
    atomic_json(args.output, {'platform': system, 'architecture': architecture, 'result': result})


if __name__ == '__main__':
    main()
