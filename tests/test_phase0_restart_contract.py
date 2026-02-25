import os
import unittest
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.restart_contract import build_restart_with_wizard_launch


class Phase0RestartContractTests(unittest.TestCase):
    def test_restart_launch_for_python_script(self):
        cmd, env = build_restart_with_wizard_launch(
            python_exe=r"C:\py\python.exe",
            argv0=r"E:\LaTexSnipper\src\main.py",
            base_env={"A": "1", "LATEXSNIPPER_DEPS_OK": "1"},
        )
        self.assertEqual(cmd[0], r"C:\py\python.exe")
        self.assertTrue(cmd[1].lower().endswith(os.path.join("src", "main.py").lower()))
        self.assertEqual(cmd[2], "--force-deps-check")
        self.assertEqual(env["LATEXSNIPPER_OPEN_WIZARD"], "1")
        self.assertEqual(env["LATEXSNIPPER_FORCE_VERIFY"], "1")
        self.assertEqual(env["LATEXSNIPPER_RESTART"], "1")
        self.assertNotIn("LATEXSNIPPER_DEPS_OK", env)

    def test_restart_launch_for_packaged_exe(self):
        cmd, env = build_restart_with_wizard_launch(
            python_exe=r"C:\py\python.exe",
            argv0=r"E:\LaTexSnipper\dist\LaTeXSnipper.exe",
            base_env={},
        )
        self.assertTrue(cmd[0].lower().endswith("latexsnipper.exe"))
        self.assertEqual(cmd[1], "--force-deps-check")
        self.assertEqual(len(cmd), 2)
        self.assertEqual(env["LATEXSNIPPER_OPEN_WIZARD"], "1")


if __name__ == "__main__":
    unittest.main()
