"""Trust release catalogs only through the product's HTTPS GitHub release metadata."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from pathlib import Path

import requests

from runtime.distribution_manifest import Artifact, ManifestError, ReleaseCatalog
from update.component_download import DownloadControl, download_component

REPOSITORY = 'SakuraMathcraft/LaTeXSnipper'
RELEASE_API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
RELEASES_PAGE = f'https://github.com/{REPOSITORY}/releases'


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    notes: str
    url: str


@dataclass(frozen=True)
class VerifiedRelease:
    catalog: ReleaseCatalog
    tag: str
    notes: str
    url: str


def _fetch_metadata(session: requests.Session, tag: str | None) -> dict:
    session.headers.update({'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
                            'User-Agent': 'LaTeXSnipper-Components'})
    if tag is not None and (not tag or '/' in tag or '\\' in tag):
        raise ManifestError('Invalid requested release tag')
    api = f'https://api.github.com/repos/{REPOSITORY}/releases/tags/{tag}' if tag else RELEASE_API
    with session.get(api, timeout=(10, 30)) as response:
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ManifestError('Invalid release metadata')
    if tag is not None and payload.get('tag_name') != tag:
        raise ManifestError('Release metadata does not match the requested tag')
    return payload


def _release_info(payload: dict) -> ReleaseInfo:
    if payload.get('draft') is not False or payload.get('prerelease') is not False:
        raise ManifestError('A component release must be a public stable release')
    tag = payload.get('tag_name')
    if not isinstance(tag, str) or not tag or '/' in tag or '\\' in tag:
        raise ManifestError('Invalid release tag')
    return ReleaseInfo(tag, str(payload.get('body') or ''), f'{RELEASES_PAGE}/tag/{tag}')


def fetch_release_info() -> ReleaseInfo:
    """Source users can read release notes without invoking component deployment."""
    with requests.Session() as session:
        return _release_info(_fetch_metadata(session, None))


def release_artifacts(payload: dict) -> dict[str, Artifact]:
    tag = _release_info(payload).tag
    entries = payload.get('assets')
    if not isinstance(entries, list):
        raise ManifestError('Release assets must be an array')
    result = {}
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str):
            raise ManifestError('Invalid release asset')
        digest = item.get('digest', '')
        if not isinstance(digest, str) or not digest.startswith('sha256:'):
            raise ManifestError('Release asset has no authoritative SHA256 digest')
        artifact = Artifact(item.get('browser_download_url'), digest.removeprefix('sha256:'), item.get('size'))
        prefix = f'https://github.com/{REPOSITORY}/releases/download/{tag}/'
        if artifact.url != prefix + item['name'] or artifact.url in result:
            raise ManifestError('Release asset URL or identity is invalid')
        result[artifact.url] = artifact
    return result


def fetch_component_release(cache: Path, *, control: DownloadControl | None = None, tag: str | None = None,
                            on_release: Callable[[ReleaseInfo], None] | None = None) -> VerifiedRelease:
    with requests.Session() as session:
        payload = _fetch_metadata(session, tag)
        info = _release_info(payload)
        if on_release is not None:
            on_release(info)
        artifacts = release_artifacts(payload)
        catalog_url = f'https://github.com/{REPOSITORY}/releases/download/{payload["tag_name"]}/desktop-release.json'
        source = artifacts.get(catalog_url)
        if source is None or source.size > 64 * 1024 * 1024:
            raise ManifestError('Release does not contain a valid desktop component catalog')
        catalog = ReleaseCatalog.load(download_component(source, cache, control=control, session=session))
        if payload['tag_name'] not in {f'v{catalog.version}', f'v{catalog.version}-LTS'}:
            raise ManifestError('Release catalog version does not match its published tag')
        for distribution in catalog.distributions:
            if distribution.release_tag != payload['tag_name']:
                raise ManifestError('Distribution tag does not match its published release')
            payloads = [*(component.artifact for component in distribution.components), distribution.installer]
            if distribution.bundle_seal is not None:
                payloads.append(distribution.bundle_seal.artifact)
            for item in payloads:
                if item is None or artifacts.get(item.url) != item:
                    raise ManifestError('Catalog artifact does not match authoritative release metadata')
        return VerifiedRelease(catalog, info.tag, info.notes, info.url)
