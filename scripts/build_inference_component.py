"""Assemble a locked standalone inference component on its target operating system."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'src')]

from distribution_archives import download_artifact
from runtime.component_archive import extract_archive
from distribution_inputs import load_sources, load_dependencies
from mathcraft_ocr.protocol import MODEL_FORMAT, WORKER_PROTOCOL
from runtime.component_inventory import file_sha256, inventory_component
from runtime.distribution_manifest import Artifact, ManifestError
from runtime.inference_probe import PROBE_CODE


def host_target() -> str:
    system = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'macos'}[platform.system()]
    machine = platform.machine().lower()
    if machine in {'arm64', 'aarch64'}:
        architecture = 'arm64'
    elif machine in {'amd64', 'x86_64', 'x64'}:
        architecture = 'x86_64'
    else:
        raise ManifestError(f'Unsupported build architecture: {machine}')
    return f'{system}-{architecture}'


def python_executable(root: Path) -> Path:
    return root / ('python.exe' if os.name == 'nt' else 'bin/python3')


def isolated_environment(root: Path, *, gpu: bool) -> dict[str, str]:
    env = os.environ.copy()
    for key in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONUSERBASE', 'PYTHONSTARTUP', 'CUDA_PATH', 'CUDA_HOME'):
        env.pop(key, None)
    env.update(PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    if gpu:
        native = str(root / 'native')
        if os.name == 'nt':
            env['PATH'] = os.pathsep.join([native, str(root), str(Path(os.environ['SystemRoot']) / 'System32')])
        elif sys.platform.startswith('linux'):
            env['LD_LIBRARY_PATH'] = os.pathsep.join([native, str(root / 'lib')])
    return env


def run_python(root: Path, code: str, arguments: list[str], *, gpu: bool = False) -> str:
    result = subprocess.run([str(python_executable(root)), '-I', '-B', '-c', code, *arguments],
                            cwd=root, env=isolated_environment(root, gpu=gpu), capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=180)
    if result.returncode:
        raise RuntimeError(f'Inference component command failed ({result.returncode}):\n{result.stdout}\n{result.stderr}')
    return result.stdout


def pip_command(root: Path, pip_wheel: Path, arguments: list[str]) -> None:
    code = "import sys; sys.path.insert(0, sys.argv[1]); from pip._internal.cli.main import main; raise SystemExit(main(sys.argv[2:]))"
    run_python(root, code, [str(pip_wheel), *arguments])


def remove_owned(path: Path, owner: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if not path.resolve().is_relative_to(owner.resolve()):
        raise ManifestError('Build cleanup escaped its staging directory')
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def install_dependencies(root: Path, entries: list[dict], tools: list[dict], cache: Path, work: Path) -> None:
    archives = {item['name']: download_artifact(Artifact.from_dict(item['artifact']), cache) for item in tools}
    pip_wheel = archives['pip']
    pip_command(root, pip_wheel, ['install', '--no-index', '--no-deps', '--no-compile', '--disable-pip-version-check', *map(str, archives.values())])
    wheels = []
    for item in entries:
        archive = download_artifact(Artifact.from_dict(item['artifact']), cache)
        if item['kind'] == 'sdist':
            output = work / 'built-wheels'
            output.mkdir(exist_ok=True)
            env = isolated_environment(root, gpu=False)
            env['SOURCE_DATE_EPOCH'] = '315532800'
            command = [str(python_executable(root)), '-I', '-B', '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation', '--no-cache-dir', '--wheel-dir', str(output), str(archive)]
            result = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            built = list(output.glob('*.whl'))
            if len(built) != 1:
                raise ManifestError('Expected exactly one source-built wheel')
            wheels.append(built[0])
        else:
            wheels.append(archive)
    pip_command(root, pip_wheel, ['install', '--no-index', '--no-deps', '--no-compile', '--disable-pip-version-check', *map(str, wheels)])
    pip_command(root, pip_wheel, ['check', '--disable-pip-version-check'])


def deploy_native_libraries(root: Path, sources: list[dict], cache: Path, work: Path) -> None:
    native = root / 'native'
    native.mkdir()
    for item in sources:
        archive = download_artifact(Artifact.from_dict(item['artifact']), cache)
        extracted = work / f'native-{item["name"]}'
        extract_archive(archive, extracted)
        libraries = []
        licenses = []
        for path in extracted.rglob('*'):
            if not path.is_file() and not path.is_symlink():
                continue
            if 'stubs' in path.parts:
                continue
            lower = path.name.lower()
            if lower.endswith('.dll') or '.so' in lower:
                libraries.append(path)
            elif any(marker in lower for marker in ('license', 'licence', 'eula', 'notice')):
                licenses.append(path)
        if not libraries or not licenses:
            raise ManifestError(f'Native source lacks runtime libraries or license: {item["name"]}')
        for source in libraries:
            target = native / source.name
            if target.exists() or target.is_symlink():
                if source.is_symlink() or file_sha256(target) != file_sha256(source):
                    raise ManifestError(f'Conflicting private runtime library: {source.name}')
                continue
            if source.is_symlink():
                link = Path(os.readlink(source)).name
                os.symlink(link, target)
            else:
                shutil.copy2(source, target)
        for source in licenses:
            target = root / 'licenses' / item['name'] / source.relative_to(extracted)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        remove_owned(extracted, work)


def prune_build_tools(root: Path) -> None:
    sites = [root / 'Lib/site-packages'] if os.name == 'nt' else list((root / 'lib').glob('python*/site-packages'))
    for site in sites:
        for path in site.iterdir():
            if path.name in {'pip', 'setuptools', 'wheel', 'pkg_resources', '_distutils_hack', 'distutils-precedence.pth'} or path.name.startswith(('pip-', 'setuptools-', 'wheel-')):
                remove_owned(path, root)
    scripts = root / ('Scripts' if os.name == 'nt' else 'bin')
    if scripts.exists():
        for path in scripts.iterdir():
            if path.name not in {'python', 'python3', 'python3.11', 'python.exe'}:
                remove_owned(path, root)
    for name in ('include', 'tcl', 'Tools', 'Doc'):
        remove_owned(root / name, root)
    for path in list(root.rglob('direct_url.json')):
        if path.parent.name.endswith('.dist-info'):
            remove_owned(path, root)
    for path in list(root.rglob('__pycache__')):
        remove_owned(path, root)
    for site in sites:
        for record in site.glob('*.dist-info/RECORD'):
            with record.open(encoding='utf-8', newline='') as stream:
                rows = list(csv.reader(stream))
            kept = [row for row in rows if row and (site / row[0]).resolve().is_relative_to(root.resolve()) and (site / row[0]).is_file()]
            with record.open('w', encoding='utf-8', newline='') as stream:
                csv.writer(stream).writerows(kept)


def assemble(args: argparse.Namespace) -> None:
    sources = load_sources(args.catalog)
    dependencies = load_dependencies(args.dependencies, sources)
    target = args.target or host_target()
    if target != host_target():
        raise ManifestError('Inference components must be assembled and verified on their target platform')
    config = sources['targets'][target]
    if args.edition == 'gpu' and config['ort_gpu'] is None:
        raise ManifestError('No GPU distribution for this target')
    output = args.output.resolve()
    if output.exists():
        raise ManifestError('Output must not contain an existing environment')
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = args.cache.resolve()
    if output == cache or output.is_relative_to(cache) or cache.is_relative_to(output):
        raise ManifestError('Build output must be separate from the download cache')
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='inference-build-', dir=output.parent) as temporary:
        work = Path(temporary)
        archive = download_artifact(Artifact.from_dict(config['python']), cache)
        extract_archive(archive, work / 'python-source')
        python_root = work / 'python-source/python'
        if not python_executable(python_root).is_file():
            raise ManifestError('Standalone Python archive has an unexpected layout')
        entries = list(dependencies['targets'][target])
        selected = config['ort_gpu'] if args.edition == 'gpu' else config['ort_cpu']
        entries.append({'name': 'onnxruntime', 'kind': 'wheel', 'artifact': selected})
        install_dependencies(python_root, entries, dependencies['build_tools'], cache, work)
        if args.edition == 'gpu':
            deploy_native_libraries(python_root, config['native_libraries'], cache, work)
        prune_build_tools(python_root)
        details = {
            'schema': 1, 'target': target, 'edition': args.edition,
            'worker_protocol': WORKER_PROTOCOL, 'model_format': MODEL_FORMAT,
            'python_version': sources['python_version'], 'ort_version': sources['ort_version'],
            'cuda_version': sources['cuda_version'] if args.edition == 'gpu' else None,
            'cudnn_version': sources['cudnn_version'] if args.edition == 'gpu' else None,
            'minimum_driver': config['minimum_driver'] if args.edition == 'gpu' else None,
            'dependencies': {item['name']: item['version'] for item in dependencies['targets'][target]},
            'native_sources': config['native_libraries'] if args.edition == 'gpu' else [],
        }
        (python_root / 'runtime.json').write_text(json.dumps(details, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        expected_gpu = args.edition == 'gpu' and args.validate_gpu
        result = run_python(python_root, PROBE_CODE, [str(python_root), 'gpu' if expected_gpu else 'cpu'], gpu=expected_gpu)
        validation = json.loads(result.strip().splitlines()[-1])
        if validation['python'] != sources['python_version'] or validation['ort'] != sources['ort_version']:
            raise ManifestError('Assembled runtime versions do not match the source lock')
        relocated = work / 'relocated-runtime'
        python_root.rename(relocated)
        moved = run_python(relocated, PROBE_CODE, [str(relocated), 'gpu' if expected_gpu else 'cpu'], gpu=expected_gpu)
        validation = json.loads(moved.strip().splitlines()[-1])
        files = inventory_component(relocated)
        relocated.rename(output)
    report = {'target': target, 'edition': args.edition, 'validation': validation,
              'gpu_validated': expected_gpu,
              'uncompressed_bytes': sum(item.size for item in files), 'file_count': len(files),
              'native_bytes': sum(item.size for item in files if item.path.startswith('native/'))}
    output.with_name(output.name + '.build.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target')
    parser.add_argument('--edition', choices=('cpu', 'gpu'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'packaging/runtime/sources.lock.json')
    parser.add_argument('--dependencies', type=Path, default=ROOT / 'packaging/runtime/dependencies.lock.json')
    parser.add_argument('--validate-gpu', action='store_true')
    assemble(parser.parse_args())


if __name__ == '__main__':
    main()
