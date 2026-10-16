"""Build-cache identities follow the files actually used by each component."""

import shutil
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_desktop_release as build


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    locks = tmp_path / 'packaging/runtime'
    locks.mkdir(parents=True)
    for name in ('sources.lock.json', 'resources.lock.json'):
        shutil.copy2(ROOT / 'packaging/runtime' / name, locks / name)
    monkeypatch.setattr(build, 'ROOT', tmp_path)
    return tmp_path


@pytest.mark.parametrize(('target', 'path', 'affected'), [
    ('windows-x86_64', 'scripts/normalize_windows_crt.ps1', {'application'}),
    ('linux-x86_64', 'scripts/linux_hotkey_packaging.py', {'application'}),
    ('linux-x86_64', 'packaging/debian/DEBIAN/control', {'application'}),
    ('linux-x86_64', 'requirements-linux.txt', {'application'}),
    ('macos-arm64', 'requirements-macos.txt', {'application'}),
    ('macos-arm64', 'packaging/macos/entitlements.plist', {'application', 'inference'}),
    ('windows-x86_64', 'src/runtime/inference_probe.py', {'application', 'inference'}),
])
def test_build_input_changes_invalidate_the_owning_components(inputs, target, path, affected):
    source = inputs / path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text('before', encoding='utf-8')
    before = build.build_inputs(target)
    source.write_text('after', encoding='utf-8')
    after = build.build_inputs(target)
    assert {name for name in before if before[name] != after[name]} == affected


def test_unrelated_platform_requirements_preserve_cached_components(inputs):
    before = build.build_inputs('windows-x86_64')
    (inputs / 'requirements-macos.txt').write_text('changed', encoding='utf-8')
    assert build.build_inputs('windows-x86_64') == before


def test_linux_application_package_owns_its_launchers_and_dependencies(tmp_path, monkeypatch):
    from dataclasses import replace
    from types import SimpleNamespace
    from build_application_resources import assemble_linux_integration
    from runtime.component_inventory import inventory_component
    from update import debian_packages
    from test_deployment_transaction import installation
    from PIL import Image

    root = tmp_path / 'payload'
    manifest = installation(root)
    application = root / 'application'
    monkeypatch.setattr(Image, 'open', lambda *args: Image.new('RGBA', (256, 256)))
    assemble_linux_integration(application / 'linux-integration')
    component = replace(manifest.component('application'), files=inventory_component(application))
    inspected = []

    def build_deb(arguments, **kwargs):
        directory = Path(arguments[-2])
        control = (directory / 'DEBIAN/control').read_text(encoding='utf-8')
        assert 'Package: latexsnipper\n' in control and 'Depends: libc6' in control
        assert (directory / 'usr/bin/latexsnipper').is_file()
        assert (directory / 'usr/lib/latexsnipper/LaTeXSnipper').is_file()
        assert (directory / 'usr/share/applications/latexsnipper.desktop').is_file()
        assert (directory / 'usr/lib/latexsnipper/application/data.bin').read_bytes() == b'application'
        inspected.append(True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(debian_packages.subprocess, 'run', build_deb)
    debian_packages.build_package(application, component, tmp_path / 'application.deb')
    assert inspected == [True]


def test_first_install_package_cleanup_preserves_the_active_transaction(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from update import debian_packages

    root = tmp_path / 'usr/lib/latexsnipper'
    root.mkdir(parents=True)
    observed = []

    def purge(arguments, **kwargs):
        assert kwargs['env']['LATEXSNIPPER_DEPLOYMENT_ACTIVE'] == '1'
        assert arguments[-3:] == ['latexsnipper', 'latexsnipper-inference', 'latexsnipper-models']
        observed.append(True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(debian_packages.subprocess, 'run', purge)
    debian_packages.purge_packages(root, ['application', 'inference', 'models'])
    assert observed == [True]


@pytest.mark.parametrize('damage', ['missing', 'corrupt'])
def test_linux_repair_can_back_up_damaged_package_metadata(tmp_path, monkeypatch, damage):
    from dataclasses import replace
    from types import SimpleNamespace
    from runtime.component_inventory import inventory_component
    from update import debian_packages
    from update.debian_transaction import DebianDeploymentTransaction
    from test_deployment_transaction import installation

    staged = tmp_path / 'staged'
    manifest = installation(staged)
    application = staged / 'application'
    control = application / 'linux-integration/DEBIAN/control'
    control.parent.mkdir(parents=True)
    control.write_text('Package: latexsnipper\nVersion: 0.0.0\n', encoding='utf-8')
    component = replace(manifest.component('application'), files=inventory_component(application))
    manifest = replace(manifest, components=(component, *manifest.components[1:]))
    root = tmp_path / 'prefix/usr/lib/latexsnipper'
    shutil.copytree(application, root / 'application')
    damaged = root / 'application/linux-integration'
    if damage == 'missing':
        shutil.rmtree(damaged)
    else:
        (damaged / 'DEBIAN/control').write_text('damaged', encoding='utf-8')
    packaged = []

    def build_deb(arguments, **kwargs):
        directory = Path(arguments[-2])
        assert (directory / 'DEBIAN/control').read_text(encoding='utf-8') == (
            f'Package: latexsnipper\nVersion: 0+{component.content_sha256}\n'
        )
        packaged.append(Path(arguments[-1]).name)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(debian_packages.subprocess, 'run', build_deb)
    transaction = DebianDeploymentTransaction(root)
    transaction.directory.mkdir()
    transaction._prepare(staged, manifest, manifest, [component])
    assert packaged == ['application.deb', 'application.deb']


def test_macos_bundle_build_uses_local_signatures(tmp_path, monkeypatch):
    from PIL import Image
    from runtime.component_inventory import verify_component
    from update import macos_transaction
    from test_deployment_transaction import installation
    from test_platform_deployment import retarget

    layout = tmp_path / 'layout'
    manifest = retarget(installation(layout), 'macos')
    signed = []

    def native_tool(arguments, **kwargs):
        if arguments[0] in {'clang', 'iconutil'}:
            Path(arguments[arguments.index('-o') + 1]).write_bytes(b'native fixture')
        elif arguments[0] == 'codesign':
            signed.append((arguments[arguments.index('--sign') + 1], Path(arguments[-1])))

    checked = []
    monkeypatch.setattr(Image, 'open', lambda *args: Image.new('RGBA', (256, 256)))
    monkeypatch.setattr(build, 'run', native_tool)
    monkeypatch.setattr(macos_transaction, 'verify_bundle', checked.append)
    bundle = build.create_macos_bundle(layout, manifest)
    assert checked == [bundle]
    assert signed == [('-', bundle / 'Contents/MacOS/LaTeXSnipper'), ('-', bundle)]
    for component in manifest.components:
        assert not verify_component(bundle / 'Contents/Resources/desktop' / component.name, component)


def test_signed_windows_installer_replaces_only_the_carrier_identity(tmp_path):
    from release_artifacts import finalize_windows
    from runtime.distribution_manifest import DistributionManifest
    from runtime.component_inventory import file_sha256
    from update.deployment_transaction import atomic_json
    from test_deployment_transaction import installation

    distribution = installation(tmp_path / 'layout')
    output, signed = tmp_path / 'output', tmp_path / 'signed'
    output.mkdir()
    signed.mkdir()
    filename = f'LaTeXSnipper_{distribution.version}_windows_x86_64_cpu.exe'
    (signed / filename).write_bytes(b'signed carrier')
    metadata = output / 'distribution-windows-x86_64-cpu.json'
    atomic_json(metadata, distribution.to_dict())
    finalize_windows(output, signed)
    final = DistributionManifest.load(metadata)
    assert final.components == distribution.components
    assert final.installer is not None
    assert final.installer.sha256 == file_sha256(signed / filename)
    assert (output / filename).read_bytes() == b'signed carrier'
