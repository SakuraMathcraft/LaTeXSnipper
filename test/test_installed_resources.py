"""Verify installation boundaries, worker launch and shared model cache selection."""

from dataclasses import replace
import hashlib
import json
import ast
from pathlib import Path
import sys
import os
from types import SimpleNamespace
import zipfile

import pytest

from mathcraft_ocr.cache import inspect_model_roots
from mathcraft_ocr.manifest import ModelFileSpec, ModelSpec, load_manifest
from mathcraft_ocr.protocol import validate_request, validate_response
from runtime.component_inventory import inventory_component
from runtime.distribution_manifest import Artifact, Component, DistributionManifest, ManifestError
import runtime.installed_resources as resources_module
from runtime.installed_resources import InstalledResources, installation_root, worker_command, worker_environment


@pytest.fixture(autouse=True)
def windows_resource_fixture(monkeypatch, tmp_path):
    import mathcraft_ocr.cache as cache_module

    monkeypatch.setattr(cache_module, 'sys', SimpleNamespace(platform='win32'))
    monkeypatch.setenv('SYSTEMROOT', str(tmp_path / 'Windows'))


def installed(tmp_path, monkeypatch, edition='cpu'):
    payloads = {
        'application': {'pandoc/pandoc.exe': b'pandoc', 'worker/mathcraft_ocr/worker.py': b'worker',
                        'worker/mathcraft_ocr/protocol.py': b'protocol', 'worker/mathcraft_ocr/runtime.py': b'runtime'},
        'inference': {'python.exe': b'python', 'runtime.json': json.dumps({
            'schema': 1, 'target': 'windows-x86_64', 'edition': edition, 'worker_protocol': 1, 'model_format': 1,
        }).encode()},
        'models': {'models.v1.json': (Path(__file__).resolve().parents[1] / 'mathcraft_ocr/manifests/models.v1.json').read_bytes()},
    }
    components = []
    for name, files in payloads.items():
        for relative, content in files.items():
            path = tmp_path / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        components.append(Component(name, 'windows', 'x86_64', edition if name == 'inference' else 'common',
                                    0 if name == 'models' else 1, 1, inventory_component(tmp_path / name),
                                    Artifact('https://example.com/' + name + '.zip', '0' * 64, 1)))
    manifest = DistributionManifest('3.1.0', 'windows', 'x86_64', edition, tuple(components))
    (tmp_path / 'distribution.json').write_text(json.dumps(manifest.to_dict()), encoding='utf-8')
    monkeypatch.setattr(resources_module, 'current_target', lambda: ('windows', 'x86_64'))
    return InstalledResources.load(tmp_path)


def test_installed_worker_launch_uses_verified_resources(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    resources = installed(tmp_path, monkeypatch, 'gpu')
    command = worker_command(resources)
    assert Path(command[0]) == resources.python
    assert command[1:4] == ['-I', '-B', '-u']
    constants = [node.value for node in ast.walk(ast.parse(command[-1])) if isinstance(node, ast.Constant)]
    assert str(tmp_path / 'application/worker') in constants
    assert "'provider_preference': 'cuda'" in command[-1]
    assert str(tmp_path / 'models') in constants
    assert str(tmp_path / 'appdata/MathCraft/models') in constants


def test_damaged_worker_cannot_launch_with_valid_interpreter(tmp_path, monkeypatch):
    resources = installed(tmp_path, monkeypatch)
    (tmp_path / 'application/worker/mathcraft_ocr/worker.py').write_bytes(b'corrupt')
    with pytest.raises(ManifestError, match='worker implementation'):
        worker_command(resources)


def test_private_worker_environment_confines_dll_search(tmp_path, monkeypatch):
    resources = installed(tmp_path, monkeypatch, 'gpu')
    monkeypatch.setenv('PATH', 'external/cuda;external/python')
    monkeypatch.setenv('PYTHONPATH', 'external/python')
    monkeypatch.setenv('CUDA_HOME', 'external/cuda')
    env = worker_environment(resources)
    assert env['PATH'].split(os.pathsep)[0] == str(tmp_path / 'inference/native')
    assert env['PYTHONNOUSERSITE'] == '1'
    assert 'PYTHONPATH' not in env
    assert 'CUDA_HOME' not in env


def test_source_worker_uses_running_developer_interpreter():
    assert worker_command(None)[0] == sys.executable
    assert "'provider_preference': 'cpu'" in worker_command(None)[-1]


def test_source_desktop_worker_uses_default_mathcraft_cache(tmp_path, monkeypatch):
    import runtime.model_resources as models_module
    from mathcraft_ocr.cache import resolve_user_models_dir

    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setenv('MATHCRAFT_HOME', str(tmp_path / 'library-cache'))
    models = models_module.desktop_model_resources(None)
    assert models.roots == (tmp_path / 'appdata/MathCraft/models',)
    assert resolve_user_models_dir() == tmp_path / 'library-cache'
    command = worker_command(None)
    constants = [node.value for node in ast.walk(ast.parse(command[-1])) if isinstance(node, ast.Constant)]
    assert str(models.cache_root) in constants


def test_packaged_model_policy_selects_repaired_weights_only_for_damaged_model(tmp_path, monkeypatch):
    import runtime.model_resources as models_module
    from mathcraft_ocr.manifest import Manifest

    resources = installed(tmp_path / 'installation', monkeypatch)
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    specs = {name: ModelSpec(name, '1', (ModelFileSpec('weights.onnx', hashlib.sha256(data).hexdigest()),), ())
             for name, data in (('formula', b'formula'), ('text', b'text'))}
    monkeypatch.setattr(models_module, 'load_manifest', lambda _path: Manifest(1, specs))
    models = models_module.desktop_model_resources(resources)
    for name, data in (('formula', b'broken'), ('text', b'text')):
        target = models.installed_root / name / 'weights.onnx'
        target.parent.mkdir()
        target.write_bytes(data)
    repaired = models.cache_root / 'formula/weights.onnx'
    repaired.parent.mkdir(parents=True)
    repaired.write_bytes(b'formula')
    states = models.inspect()
    assert states['formula'].complete and states['text'].complete
    assert states['formula'].model_dir == models.cache_root / 'formula'
    assert states['text'].model_dir == models.installed_root / 'text'


@pytest.mark.parametrize('installed_content', [None, b'corrupt'])
@pytest.mark.parametrize('cached_content', [b'current', b'outdated', None])
def test_desktop_model_fallback_reuses_or_repairs_shared_cache(
    tmp_path, monkeypatch, installed_content, cached_content,
):
    import runtime.model_resources as models_module
    from mathcraft_ocr.manifest import Manifest
    from mathcraft_ocr.runtime import MathCraftRuntime

    resources = installed(tmp_path / 'installation', monkeypatch)
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    archive = tmp_path / 'model.zip'
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr('formula/weights.onnx', b'current')
    spec = ModelSpec('formula', '1', (
        ModelFileSpec('weights.onnx', hashlib.sha256(b'current').hexdigest()),
    ), (archive.as_uri(),))
    manifest = Manifest(1, {'formula': spec})
    monkeypatch.setattr(models_module, 'load_manifest', lambda _path: manifest)
    models = models_module.desktop_model_resources(resources)
    bundled_file = models.installed_root / 'formula/weights.onnx'
    cached_file = models.cache_root / 'formula/weights.onnx'
    for file, content in ((bundled_file, installed_content), (cached_file, cached_content)):
        if content is not None:
            file.parent.mkdir(parents=True)
            file.write_bytes(content)
    runtime = MathCraftRuntime(
        manifest=manifest, bundled_models_dir=models.installed_root, cache_dir=models.cache_root,
    )
    state = runtime._ensure_selected_models(('formula',))['formula']
    assert state.complete and state.model_dir == models.cache_root / 'formula'
    assert cached_file.read_bytes() == b'current'
    assert bool(runtime._cache_events) == (cached_content != b'current')
    if installed_content is not None:
        assert bundled_file.read_bytes() == installed_content


def test_valid_installed_model_is_selected_before_inspecting_shared_cache(tmp_path, monkeypatch):
    import mathcraft_ocr.cache as cache_module

    path = tmp_path / 'installed/formula/weights.onnx'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'current')
    spec = ModelSpec('formula', '1', (
        ModelFileSpec('weights.onnx', hashlib.sha256(b'current').hexdigest()),
    ), ())
    inspected = []
    inspect = cache_module.inspect_model_cache

    def record(root, model):
        inspected.append(root)
        return inspect(root, model)

    monkeypatch.setattr(cache_module, 'inspect_model_cache', record)
    state = inspect_model_roots((tmp_path / 'installed', tmp_path / 'shared-cache'), spec)
    assert state.complete and state.model_dir == path.parent
    assert inspected == [tmp_path / 'installed']


@pytest.mark.parametrize('system, expected', [
    ('win32', 'appdata/MathCraft/models'),
    ('linux', 'xdg-data/LaTeXSnipper/MathCraft/models'),
    ('darwin', 'home/Library/Application Support/LaTeXSnipper/MathCraft/models'),
])
def test_desktop_model_cache_follows_platform_default(tmp_path, monkeypatch, system, expected):
    import mathcraft_ocr.cache as cache_module
    from runtime.model_resources import desktop_model_resources

    monkeypatch.setattr(cache_module.sys, 'platform', system)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'home')
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg-data'))
    assert desktop_model_resources(None).cache_root == tmp_path / expected


def test_inference_metadata_cannot_change_installation_edition(tmp_path, monkeypatch):
    resources = installed(tmp_path, monkeypatch)
    path = tmp_path / 'inference/runtime.json'
    details = json.loads(path.read_text())
    details['edition'] = 'gpu'
    path.write_text(json.dumps(details))
    inference = replace(resources.manifest.component('inference'), files=inventory_component(tmp_path / 'inference'))
    resources = replace(resources, manifest=replace(resources.manifest, components=tuple(inference if item.name == 'inference' else item for item in resources.manifest.components)))
    with pytest.raises(ManifestError, match='installation contract'):
        resources.verify_runtime()


def test_model_roots_skip_corrupt_and_obsolete_contents(tmp_path):
    bundled, cache = tmp_path / 'models', tmp_path / 'repair'
    for root, data in ((bundled, b'broken'), (cache, b'old')):
        path = root / 'formula/weights.onnx'
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
    spec = ModelSpec('formula', '1', (ModelFileSpec('weights.onnx', hashlib.sha256(b'new').hexdigest()),), ())
    assert not inspect_model_roots((bundled, cache), spec).complete
    (cache / 'formula/weights.onnx').write_bytes(b'new')
    assert inspect_model_roots((bundled, cache), spec).model_dir == cache / 'formula'
    (bundled / 'formula/weights.onnx').write_bytes(b'new')
    assert inspect_model_roots((bundled, cache), spec).model_dir == bundled / 'formula'
    assert replace(spec, files=(ModelFileSpec('weights.onnx', '0' * 64),)).content_sha256 != spec.content_sha256


def test_model_integrity_checks_current_bytes_with_preserved_size_and_timestamp(tmp_path):
    import os
    from mathcraft_ocr.cache import model_file_valid

    weights = tmp_path / 'weights.onnx'
    weights.write_bytes(b'valid')
    digest = hashlib.sha256(b'valid').hexdigest()
    metadata = weights.stat()
    assert model_file_valid(tmp_path, weights.name, digest)
    weights.write_bytes(b'wrong')
    os.utime(weights, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    assert not model_file_valid(tmp_path, weights.name, digest)


@pytest.mark.parametrize('protocol', [None, True, '1', 2])
def test_worker_contract_rejects_unsupported_protocol(protocol):
    with pytest.raises(ValueError, match='protocol'):
        validate_request({'protocol': protocol, 'id': '1', 'action': 'warmup'})


def test_worker_contract_checks_response_correlation():
    with pytest.raises(ValueError, match='id'):
        validate_response({'protocol': 1, 'id': 'other', 'ok': True, 'result': {}}, '1')
    assert validate_response({'protocol': 1, 'id': '1', 'ok': True, 'result': {}}, '1')['ok']


def test_model_manifest_rejects_traversal_before_download(tmp_path):
    data = json.loads((Path(__file__).resolve().parents[1] / 'mathcraft_ocr/manifests/models.v1.json').read_text())
    data['models']['mathcraft-formula-det']['files'][0]['path'] = '../outside.onnx'
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(data))
    from mathcraft_ocr.errors import ManifestError as ModelManifestError

    with pytest.raises(ModelManifestError, match='unsafe'):
        load_manifest(path)


def test_macos_resource_layout_is_inside_bundle():
    executable = Path('/Applications/LaTeXSnipper.app/Contents/Resources/desktop/application/LaTeXSnipper')
    assert installation_root(executable) == executable.resolve().parent.parent
