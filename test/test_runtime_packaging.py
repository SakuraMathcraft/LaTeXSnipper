# pyright: reportMissingImports=false

import re
import unittest
from pathlib import Path


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
