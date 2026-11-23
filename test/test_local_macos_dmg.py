"""Regression coverage for the local DMG workspace and stage cache."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/release"))

import build_macos_dmg as build  # noqa: E402


def test_unowned_workspace_preserves_existing_files(tmp_path):
    work = tmp_path / "work"
    existing = work / "runtime" / "notes.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("keep", encoding="utf-8")

    with pytest.raises(build.ManifestError, match="Choose an empty"):
        build.prepare_workspace(work, tmp_path / "downloads", tmp_path / "dist")

    assert existing.read_text(encoding="utf-8") == "keep"


def test_workspace_keeps_download_cache_outside_cleaned_stages(tmp_path):
    work = tmp_path / "work"
    cache = work / "runtime" / "downloads"
    with pytest.raises(build.ManifestError, match="inside a build stage"):
        build.prepare_workspace(work, cache, tmp_path / "dist")


def test_local_environment_changes_invalidate_runtime_and_base(monkeypatch):
    keys = dict.fromkeys(
        ("runtime", "maintenance", "inference-cpu", "models-cpu", "base"), "locked"
    )
    monkeypatch.setattr(build, "build_inputs", lambda *_: keys.copy())
    monkeypatch.setattr(build, "distributions", lambda: [])
    before = build.stage_inputs("macos-arm64")
    monkeypatch.setattr(sys, "version", "3.11.15 (updated local build)")
    after = build.stage_inputs("macos-arm64")

    assert {name for name in before if before[name] != after[name]} == {
        "runtime",
        "maintenance",
        "inference",
        "base",
    }


def test_stage_reuses_matching_payload_and_rebuilds_after_failure_or_change(tmp_path):
    work = tmp_path / "work"
    build.prepare_workspace(work, tmp_path / "downloads", tmp_path / "dist")
    keep = work / "notes.txt"
    keep.write_text("keep", encoding="utf-8")
    directory = work / "runtime"
    payload = directory / "payload"

    def assemble(destination):
        destination.mkdir()
        (destination / "runtime").write_text("ready", encoding="utf-8")

    def fail(destination):
        assemble(destination)
        (destination / "partial").touch()
        raise RuntimeError("interrupted")

    def run(key, builder=assemble, *, force=False):
        return build.build_cached_stage(
            directory, key, builder, force=force, signed=False
        )

    with pytest.raises(RuntimeError, match="interrupted"):
        run("first", fail)
    assert run("first")
    assert list(payload.iterdir()) == [payload / "runtime"]
    assert not run("first", fail)
    assert run("second")
    assert run("second", force=True)
    assert keep.read_text(encoding="utf-8") == "keep"
