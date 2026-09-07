# pyright: reportMissingImports=false

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TestMathcraftPackageMetadata(unittest.TestCase):
    def test_mathcraft_package_version_matches_public_init(self):
        import mathcraft_ocr

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.group(1), mathcraft_ocr.__version__)
