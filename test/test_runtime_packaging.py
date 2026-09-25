# pyright: reportMissingImports=false

import ast
import os
import re
import unittest
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


class TestRuntimePackaging(unittest.TestCase):
    def test_pyinstaller_spec_keeps_psutil_for_packaged_speed_meter(self):
        spec = (ROOT / "LaTeXSnipper.spec").read_text(encoding="utf-8")
        hiddenimports = re.search(r"hiddenimports=\[(.*?)\],", spec, re.S)
        excludes = re.search(r"excludes=\[(.*?)\],", spec, re.S)
        prune_prefixes = re.search(r"remove_prefixes = \((.*?)\)", spec, re.S)

        self.assertIsNotNone(hiddenimports)
        self.assertIsNotNone(excludes)
        self.assertIsNotNone(prune_prefixes)
        self.assertIn('"psutil"', hiddenimports.group(1))
        self.assertNotIn('"psutil"', excludes.group(1))
        self.assertNotIn('"psutil"', prune_prefixes.group(1))


def run_seed_collection():
    """Execute the spec's seed-input boundary without invoking PyInstaller."""
    path = ROOT / "LaTeXSnipper.spec"
    nodes = ast.parse(path.read_text(encoding="utf-8")).body
    start = next(
        i
        for i, node in enumerate(nodes)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "bundled_python" for t in node.targets
        )
    )
    end = next(
        i
        for i, node in enumerate(nodes[start:], start)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "a" for t in node.targets)
    )
    namespace = {
        "os": os,
        "Path": Path,
        "extra_datas": [],
        "_collect_tree_as_datas": lambda source, destination: [(source, destination)],
    }
    exec(
        compile(ast.Module(body=nodes[start:end], type_ignores=[]), str(path), "exec"),
        namespace,
    )
    return namespace["extra_datas"]


def test_windows_bundle_collects_explicit_seed_path(tmp_path, monkeypatch):
    seed = tmp_path / "runner inputs" / "python seed"
    seed.mkdir(parents=True)
    (seed / "python.exe").touch()
    monkeypatch.setenv("LATEXSNIPPER_BUNDLED_PYTHON", str(seed))
    assert run_seed_collection() == [(seed.resolve(), "deps/python311")]


def test_windows_bundle_requires_usable_seed(tmp_path, monkeypatch):
    monkeypatch.delenv("LATEXSNIPPER_BUNDLED_PYTHON", raising=False)
    with pytest.raises(RuntimeError, match="must identify"):
        run_seed_collection()
    monkeypatch.setenv("LATEXSNIPPER_BUNDLED_PYTHON", str(tmp_path))
    with pytest.raises(RuntimeError, match="missing python.exe"):
        run_seed_collection()
