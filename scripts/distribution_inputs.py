"""Validate locked production inputs before any download or build mutation."""

from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from runtime.distribution_manifest import Artifact, ManifestError, read_json

TARGETS = frozenset({'windows-x86_64', 'linux-x86_64', 'macos-arm64'})


def fields(value: object, expected: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ManifestError(f'Expected input fields: {sorted(expected)}')
    return value


def version(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', value):
        raise ManifestError('Invalid locked version')
    return value


def artifact(value: object, *, host: str, suffix: str, prefix: str = '') -> Artifact:
    result = Artifact.from_dict(value)
    url = urlsplit(result.url)
    if url.hostname != host or not url.path.endswith(suffix) or not url.path.startswith(prefix) or url.query:
        raise ManifestError(f'Unexpected production source: {result.url}')
    return result


def load_sources(path: Path) -> dict:
    lock = fields(read_json(path), {'schema', 'python_version', 'ort_version', 'cuda_version', 'cudnn_version', 'targets'})
    if type(lock['schema']) is not int or lock['schema'] != 1:
        raise ManifestError('Unsupported source lock schema')
    for key in ('python_version', 'ort_version', 'cuda_version', 'cudnn_version'):
        version(lock[key])
    targets = fields(lock['targets'], set(TARGETS))
    libraries = {'cuda_cudart', 'libcublas', 'libcufft', 'libcurand', 'cuda_nvrtc', 'libnvjitlink', 'cudnn'}
    for target, config in targets.items():
        fields(config, {'python', 'ort_cpu', 'ort_gpu', 'minimum_driver', 'native_libraries'})
        python = artifact(config['python'], host='github.com', suffix='.tar.gz', prefix='/astral-sh/python-build-standalone/releases/download/')
        if f'cpython-{lock["python_version"]}+' not in unquote(python.url):
            raise ManifestError('Python source version does not match its lock')
        cpu = artifact(config['ort_cpu'], host='files.pythonhosted.org', suffix='.whl')
        if f'/onnxruntime-{lock["ort_version"]}-' not in cpu.url:
            raise ManifestError('CPU wheel version does not match its lock')
        sources = config['native_libraries']
        if not isinstance(sources, list):
            raise ManifestError('Native sources must be an array')
        if target.startswith('macos'):
            if config['ort_gpu'] is not None or config['minimum_driver'] is not None or sources:
                raise ManifestError('macOS requires CPU sources')
        else:
            gpu = artifact(config['ort_gpu'], host='files.pythonhosted.org', suffix='.whl')
            if f'/onnxruntime_gpu-{lock["ort_version"]}-' not in gpu.url:
                raise ManifestError('GPU wheel version does not match its lock')
            driver = config['minimum_driver']
            if not isinstance(driver, list) or len(driver) != 2 or any(type(part) is not int or part < 0 for part in driver):
                raise ManifestError('GPU target needs a driver baseline')
            if len(sources) != len(libraries) or {item.get('name') for item in sources if isinstance(item, dict)} != libraries:
                raise ManifestError('Incomplete native runtime source set')
        for source in sources:
            fields(source, {'name', 'version', 'license', 'artifact'})
            version(source['version'])
            if source['license'] not in {'CUDA Toolkit', 'cudnn'}:
                raise ManifestError('Native source needs a license reference')
            artifact(source['artifact'], host='developer.download.nvidia.com', suffix='.zip' if target.startswith('windows') else '.tar.xz')
    return lock


def load_dependencies(path: Path, sources: dict) -> dict:
    lock = fields(read_json(path), {'schema', 'python_version', 'requirements', 'build_tools', 'targets'})
    if type(lock['schema']) is not int or lock['schema'] != 1 or lock['python_version'] != sources['python_version']:
        raise ManifestError('Dependency lock does not match the standalone Python')
    if not isinstance(lock['requirements'], list) or not lock['requirements'] or not all(isinstance(item, str) and item for item in lock['requirements']):
        raise ManifestError('Invalid dependency requirements')
    fields(lock['targets'], set(TARGETS))
    for target, entries in {'build-tools': lock['build_tools'], **lock['targets']}.items():
        if not isinstance(entries, list) or not entries:
            raise ManifestError(f'Empty dependency set: {target}')
        names = set()
        for entry in entries:
            fields(entry, {'name', 'version', 'kind', 'artifact'})
            name = entry['name']
            if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or name in names:
                raise ManifestError('Invalid or duplicate dependency name')
            names.add(name)
            version(entry['version'])
            if entry['kind'] not in {'wheel', 'sdist'} or (entry['kind'] == 'sdist' and name != 'antlr4-python3-runtime'):
                raise ManifestError('Unexpected source build')
            source = artifact(entry['artifact'], host='files.pythonhosted.org', suffix='.whl' if entry['kind'] == 'wheel' else '.tar.gz')
            filename = urlsplit(source.url).path.rsplit('/', 1)[-1]
            if not filename.lower().replace('_', '-').startswith((name + '-' + entry['version']).lower()):
                raise ManifestError('Dependency artifact identity does not match its lock')
        if target == 'build-tools' and names != {'pip', 'setuptools', 'wheel'}:
            raise ManifestError('Incomplete source build tools')
        if target != 'build-tools' and names & {'onnxruntime', 'onnxruntime-gpu'}:
            raise ManifestError('ORT belongs to the selected inference variant')
    return lock


def load_resources(path: Path) -> dict:
    lock = fields(read_json(path), {'schema', 'model_format', 'model_manifest', 'models', 'pandoc_version', 'pandoc', 'licenses'})
    if type(lock['schema']) is not int or lock['schema'] != 1 or type(lock['model_format']) is not int or lock['model_format'] != 1:
        raise ManifestError('Unsupported resource lock schema or model format')
    prefix = '/SakuraMathcraft/MathCraft-Models/releases/download/'
    manifest = artifact(lock['model_manifest'], host='github.com', prefix=prefix, suffix='/models.v1.json')
    model_ids = {'mathcraft-formula-det', 'mathcraft-formula-rec', 'mathcraft-text-det', 'mathcraft-text-rec'}
    fields(lock['models'], model_ids)
    for model_id, source in lock['models'].items():
        item = artifact(source, host='github.com', prefix=prefix, suffix=f'/{model_id}.zip')
        if item.url.rsplit('/', 1)[0] != manifest.url.rsplit('/', 1)[0]:
            raise ManifestError('Model archive and manifest release mismatch')
    version(lock['pandoc_version'])
    fields(lock['pandoc'], set(TARGETS))
    for target, source in lock['pandoc'].items():
        ending = {'windows-x86_64': 'windows-x86_64.zip', 'linux-x86_64': 'linux-amd64.tar.gz', 'macos-arm64': 'arm64-macOS.zip'}[target]
        artifact(source, host='github.com', prefix=f'/jgm/pandoc/releases/download/{lock["pandoc_version"]}/', suffix=f'/pandoc-{lock["pandoc_version"]}-{ending}')
    fields(lock['licenses'], {'models', 'pandoc'})
    for name, source in lock['licenses'].items():
        item = artifact(source, host='raw.githubusercontent.com', suffix='/LICENSE' if name == 'models' else '/COPYING.md')
        repo = 'SakuraMathcraft/MathCraft-Models' if name == 'models' else 'jgm/pandoc'
        if not re.fullmatch('/' + repo + r'/[0-9a-f]{40}/[^/]+', urlsplit(item.url).path):
            raise ManifestError('License source needs a pinned upstream commit')
    return lock
