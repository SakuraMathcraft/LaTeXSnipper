"""Exercise cache retention and task ownership for each desktop platform."""

import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime import app_paths
from runtime.distribution_manifest import read_json
from runtime.installation_layout import deployment_directory
from update import cache_cleanup
from update.deployment_transaction import atomic_json


@pytest.fixture(params=["windows", "linux", "macos"])
def cache(tmp_path, monkeypatch, request):
    system = request.param
    home = tmp_path.resolve() / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(
        app_paths,
        "sys",
        SimpleNamespace(
            platform={"windows": "win32", "linux": "linux", "macos": "darwin"}[system]
        ),
    )
    monkeypatch.setattr(app_paths, "_APP_STATE_DIR_CACHE", None)
    monkeypatch.setattr(cache_cleanup, "current_target", lambda: (system, "x86_64"))
    root = (
        tmp_path
        / {
            "windows": "installed",
            "linux": "prefix/usr/lib/latexsnipper",
            "macos": "LaTeXSnipper.app/Contents/Resources/desktop",
        }[system]
    )
    root.mkdir(parents=True)
    state = app_paths.app_state_dir()
    atomic_json(state / "history.json", {"history": ["x^2"]})
    result = app_paths.app_cache_dir()
    expected = (
        home / "Library/Caches/LaTeXSnipper"
        if system == "macos"
        else home / ".latexsnipper/cache"
    )
    assert result == expected
    yield result, root, system
    assert read_json(state / "history.json") == {"history": ["x^2"]}


def age(path, seconds):
    modified = time.time() - seconds
    for item in [*path.rglob("*"), path]:
        os.utime(item, (modified, modified))


def test_download_cleanup_keeps_recent_resume_and_unowned_files(cache):
    directory, _, _ = cache
    downloads = directory / "components"
    for name, filename in (
        ("consumed", "payload"),
        ("expired", "payload.part"),
        ("recent", "payload.part"),
        ("unowned", "notes.txt"),
    ):
        parent = downloads / name
        parent.mkdir(parents=True)
        (parent / filename).write_bytes(name.encode("ascii"))
    age(downloads / "expired", cache_cleanup.DOWNLOAD_RETENTION_SECONDS + 60)
    cache_cleanup.cleanup_update_cache()
    assert sorted(path.name for path in downloads.iterdir()) == ["recent", "unowned"]
    assert (downloads / "recent/payload.part").read_bytes() == b"recent"
    assert (downloads / "unowned/notes.txt").read_bytes() == b"unowned"


@pytest.mark.parametrize("state", ["failed", "rolled-back", "committed"])
def test_finished_deployment_releases_its_task_and_staging(cache, state):
    directory, root, _ = cache
    staging = directory / "component-update-finished/staged"
    staging.mkdir(parents=True)
    task = directory / "deployment-finished"
    task.mkdir()
    atomic_json(
        task / "request.json",
        {
            "root": str(root),
            "staged": str(staging),
            "wait_pid": os.getpid(),
            "recover": False,
        },
    )
    atomic_json(task / "deployment-result.json", {"state": state})
    cache_cleanup.cleanup_update_cache()
    assert list(directory.iterdir()) == []


@pytest.mark.parametrize("owner", ["helper", "watcher", "transaction"])
def test_live_deployment_preserves_staging_and_transaction(cache, owner):
    directory, root, system = cache
    staging = directory / "component-update-live/staged"
    staging.mkdir(parents=True)
    content = staging / "business.bin"
    content.write_bytes(b"verified business")
    age(staging.parent, cache_cleanup.ORPHAN_RETENTION_SECONDS + 60)
    task = directory / "deployment-live"
    task.mkdir()
    atomic_json(
        task / "request.json",
        {"root": str(root), "staged": str(staging), "recover": False},
    )
    result = {"state": "failed" if owner == "watcher" else "ready"}
    if owner == "helper":
        result["pid"] = os.getpid()
    elif owner == "watcher":
        atomic_json(task / "watcher.json", {"pid": os.getpid()})
    else:
        deployment_directory(root, system).mkdir()
        atomic_json(
            deployment_directory(root, system) / "journal.json", {"status": "applying"}
        )
    atomic_json(task / "deployment-result.json", result)
    cache_cleanup.cleanup_update_cache()
    assert content.read_bytes() == b"verified business"
    assert task.is_dir()
    if owner == "transaction":
        assert (deployment_directory(root, system) / "journal.json").is_file()


def test_orphan_cleanup_retains_fresh_and_unowned_directories(cache):
    directory, _, _ = cache
    old = directory / "component-update-orphan"
    old.mkdir()
    age(old, cache_cleanup.ORPHAN_RETENTION_SECONDS + 60)
    fresh = directory / "component-update-fresh"
    fresh.mkdir()
    unowned = directory / "user-export"
    unowned.mkdir()
    cache_cleanup.cleanup_update_cache()
    assert sorted(path.name for path in directory.iterdir()) == [
        fresh.name,
        unowned.name,
    ]
