"""Retain immutable fixed resources in draft build-cache releases, beyond Actions cache expiry."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from runtime.distribution_manifest import ManifestError

logger = logging.getLogger("latexsnipper.desktop_base_cache")


def cache_tag(name: str, target: str, key: str) -> str:
    return f"desktop-base-{target}-{name}-{key}"


def exists(tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--json", "isDraft"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode:
        if result.stderr.strip() == "release not found":
            return False
        raise ManifestError(f"Cannot read fixed-resource cache: {result.stderr}")
    release = json.loads(result.stdout)
    if not release.get("isDraft"):
        raise ManifestError("Fixed resources must use a private draft build cache")
    return True


def restore(directory: Path, tag: str) -> None:
    directory.mkdir(parents=True)
    subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--dir",
            str(directory),
            "--pattern",
            "*.zip",
            "--pattern",
            "stamp.json",
        ],
        check=True,
    )


def store(directory: Path, tag: str) -> None:
    archives = list(directory.glob("*.zip"))
    if len(archives) != 1:
        raise ManifestError("Fixed-resource cache needs exactly one archive")
    result = subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            "--draft",
            "--target",
            os.environ["GITHUB_SHA"],
            "--title",
            tag,
            "--notes",
            "Immutable desktop build input. Used only by GitHub Actions.",
            str(directory / "stamp.json"),
            str(archives[0]),
        ],
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if result.returncode == 0:
        return
    error = result.stderr.strip()
    if error.startswith("HTTP 403:") and error.endswith("/releases)"):
        logger.warning("Could not store draft build cache %s: %s", tag, error)
        return
    raise ManifestError(f"Cannot write fixed-resource cache: {error}")
