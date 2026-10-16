"""Read the independent updater's outcome from its confined transient cache."""

import logging
import os
from pathlib import Path
import shutil

from runtime.app_paths import app_cache_dir
from runtime.distribution_manifest import ManifestError, read_json

logger = logging.getLogger(f'latexsnipper.{__name__}')


def consume_deployment_result() -> tuple[dict, Path] | None:
    value = os.environ.pop('LATEXSNIPPER_DEPLOYMENT_RESULT', None)
    if value is None:
        return None
    path = Path(value)
    cache = app_cache_dir().resolve()
    if path.is_symlink() or path.parent.is_symlink() or path.resolve().parent.parent != cache or path.name != 'deployment-result.json':
        raise ManifestError('Deployment result must belong to the application task cache')
    result = read_json(path)
    if result.get('state') not in {'committed', 'rolled-back', 'failed'}:
        raise ManifestError('Deployment did not report a final outcome')
    logger.info('独立部署结果 state=%s error=%s', result['state'], result.get('error', ''))
    return result, path.parent


def cleanup_deployment_task(directory: Path) -> bool:
    cache = app_cache_dir().resolve()
    if directory.is_symlink() or directory.resolve().parent != cache:
        raise ManifestError('Deployment cleanup escaped the task cache')
    if not directory.exists():
        return True
    request_path = directory / 'request.json'
    request = read_json(request_path) if request_path.is_file() else {'recover': True}
    if not request.get('recover'):
        staging = Path(request['staged']).parent
        if staging.is_symlink() or staging.resolve().parent != cache or not staging.name.startswith('component-update-'):
            raise ManifestError('Deployment staging escaped the task cache')
        if staging.exists():
            shutil.rmtree(staging)
    try:
        shutil.rmtree(directory)
        return True
    except PermissionError:
        # Windows may still have the watcher executable open briefly. The UI
        # schedules bounded retries; it never blocks on a process or deletion.
        return False
