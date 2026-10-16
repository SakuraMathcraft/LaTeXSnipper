"""Exercise catalog provenance, resumable payloads and non-destructive staging."""

from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import threading
import zipfile

import pytest

from runtime.distribution_manifest import Artifact, DistributionManifest, ManifestError
from update.component_download import DownloadCancelled, DownloadControl, download_component
from update.component_release import REPOSITORY, release_artifacts
from update.component_staging import prepare_components
from test_distribution_components import component, distribution


class Response:
    def __init__(self, payload, status=200, content_range=None):
        self.payload = payload
        self.status_code = status
        self.headers = {'Content-Range': content_range} if content_range else {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def raise_for_status(self):
        pass

    def iter_content(self, _size):
        yield self.payload


class Session:
    def __init__(self, response):
        self.response = response
        self.headers = []

    def get(self, _url, **kwargs):
        self.headers.append(kwargs['headers'])
        return self.response

    def close(self):
        pass


def artifact(payload):
    return Artifact('https://example.com/payload.zip', hashlib.sha256(payload).hexdigest(), len(payload))


def test_component_download_reuses_only_a_verified_cache(tmp_path):
    data = b'valid component'
    source = artifact(data)
    session = Session(Response(data))
    path = download_component(source, tmp_path, session=session)
    assert path.read_bytes() == data
    assert download_component(source, tmp_path, session=session) == path
    assert len(session.headers) == 1
    path.write_bytes(b'broken component')
    assert download_component(source, tmp_path, session=session).read_bytes() == data
    assert len(session.headers) == 2


def test_component_download_resumes_exact_byte_range(tmp_path):
    data = b'first and remaining bytes'
    source = artifact(data)
    directory = tmp_path / source.sha256
    directory.mkdir()
    (directory / 'payload.part').write_bytes(data[:5])
    session = Session(Response(data[5:], 206, f'bytes 5-{len(data)-1}/{len(data)}'))
    assert download_component(source, tmp_path, session=session).read_bytes() == data
    assert session.headers == [{'Range': 'bytes=5-'}]


def test_component_download_restarts_when_server_ignores_range(tmp_path):
    data = b'complete replacement'
    source = artifact(data)
    directory = tmp_path / source.sha256
    directory.mkdir()
    (directory / 'payload.part').write_bytes(b'partial')
    assert download_component(source, tmp_path, session=Session(Response(data))).read_bytes() == data


@pytest.mark.parametrize('response', [Response(b'bad content'), Response(b'payload', 206, 'bytes 2-8/9')])
def test_component_integrity_failures_cannot_enter_complete_cache(tmp_path, response):
    source = artifact(b'new content')
    with pytest.raises(ManifestError):
        download_component(source, tmp_path, session=Session(response))
    assert not (tmp_path / source.sha256 / 'payload').is_file()


def test_paused_component_download_can_be_cancelled():
    control = DownloadControl()
    control.pause(True)
    entered, done = threading.Event(), threading.Event()
    result = []

    def checkpoint():
        entered.set()
        try:
            control.checkpoint()
        except DownloadCancelled:
            result.append('cancelled')
        done.set()

    thread = threading.Thread(target=checkpoint)
    thread.start()
    assert entered.wait(1)
    assert not done.wait(0.05)
    control.cancel()
    assert done.wait(1)
    thread.join()
    assert result == ['cancelled']


def test_release_assets_are_tied_to_authoritative_product_source():
    payload = {'draft': False, 'prerelease': False, 'tag_name': 'v3.1.0', 'assets': [{
        'name': 'desktop-release.json', 'digest': 'sha256:' + 'a' * 64, 'size': 300,
        'browser_download_url': f'https://github.com/{REPOSITORY}/releases/download/v3.1.0/desktop-release.json',
    }]}
    assert len(release_artifacts(payload)) == 1
    payload['assets'][0]['browser_download_url'] = 'https://example.com/desktop-release.json'
    with pytest.raises(ManifestError, match='URL'):
        release_artifacts(payload)


def payload_component(name, data):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as package:
        info = zipfile.ZipInfo('resource.bin')
        info.external_attr = 0o644 << 16
        package.writestr(info, data)
    payload = stream.getvalue()
    return replace(component(name, data), artifact=artifact(payload)), payload


def test_staging_only_downloads_changed_component_and_preserves_live_files(tmp_path, monkeypatch):
    root = tmp_path / 'installed'
    installed = distribution()
    for name in ('application', 'inference', 'models'):
        directory = root / name
        directory.mkdir(parents=True)
        (directory / 'resource.bin').write_bytes(b'original')
    (root / 'distribution.json').write_text(json.dumps(installed.to_dict()))
    application, archive = payload_component('application', b'new app')
    target = replace(distribution('4.0.0'), components=tuple(application if item.name == 'application' else item for item in installed.components))
    session = Session(Response(archive))
    monkeypatch.setattr('update.component_download.requests.Session', lambda: session)
    output = tmp_path / 'staged'
    plan = prepare_components(root, target, output, tmp_path / 'cache')
    assert [item.name for item in plan.downloads] == ['application']
    assert (output / 'application/resource.bin').read_bytes() == b'new app'
    assert (root / 'application/resource.bin').read_bytes() == b'original'
    assert DistributionManifest.load(output / 'distribution.json') == target
    assert session.headers == [{}]


def test_component_inventory_detects_unlisted_executable(tmp_path):
    from runtime.component_inventory import verify_component

    (tmp_path / 'resource.bin').write_bytes(b'original')
    (tmp_path / 'sitecustomize.py').write_text('print("foreign runtime")')
    assert verify_component(tmp_path, component('inference')) == ('sitecustomize.py',)
