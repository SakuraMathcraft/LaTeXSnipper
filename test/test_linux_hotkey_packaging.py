from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
VERIFIER = ROOT / "scripts" / "verify_linux_hotkey_archive.py"


if str(SCRIPTS_DIR) in sys.path:
    sys.path.remove(str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import linux_hotkey_packaging  # noqa: E402

PYNPUT_MODULES = (
    "pynput",
    "pynput._util",
    "pynput._util.xorg",
    "pynput._util.xorg_keysyms",
    "pynput.keyboard",
    "pynput.keyboard._base",
    "pynput.keyboard._xorg",
    "pynput.mouse",
    "pynput.mouse._base",
    "pynput.mouse._xorg",
)
XLIB_CORE_MODULES = (
    "Xlib",
    "Xlib.X",
    "Xlib.XK",
    "Xlib.display",
    "Xlib.ext",
    "Xlib.keysymdef",
    "Xlib.protocol",
    "Xlib.protocol.rq",
    "Xlib.support",
    "Xlib.support.connect",
    "Xlib.support.lock",
    "Xlib.support.unix_connect",
    "Xlib.threaded",
)
XLIB_EXTENSION_NAMES = (
    "composite damage dpms ge nvcontrol randr record res screensaver security "
    "shape xfixes xinerama xinput xtest"
).split()
XLIB_KEYSYM_GROUP_NAMES = (
    "apl arabic cyrillic greek hebrew katakana korean latin1 latin2 latin3 "
    "latin4 miscellany publishing special technical thai xf86 xk3270 xkb"
).split()
EXPECTED_REQUIRED_MODULES = frozenset(
    PYNPUT_MODULES
    + XLIB_CORE_MODULES
    + tuple(f"Xlib.ext.{name}" for name in XLIB_EXTENSION_NAMES)
    + tuple(f"Xlib.keysymdef.{name}" for name in XLIB_KEYSYM_GROUP_NAMES)
)
PYNPUT_BACKEND_ENV_VARS = (
    "PYNPUT_BACKEND",
    "PYNPUT_BACKEND_KEYBOARD",
    "PYNPUT_BACKEND_MOUSE",
)


class LinuxHotkeyModuleCollectorTests(unittest.TestCase):
    def _collector(
        self,
        *,
        missing: str | None = None,
        observed: list[dict[str, str | None]] | None = None,
    ):
        def collect_submodules(package: str, *, on_error: str) -> list[str]:
            self.assertEqual(on_error, "raise")
            if observed is not None:
                observed.append(
                    {name: os.environ.get(name) for name in PYNPUT_BACKEND_ENV_VARS}
                )
            return sorted(
                module
                for module in EXPECTED_REQUIRED_MODULES
                if module != missing
                and (module == package or module.startswith(f"{package}."))
            )

        return collect_submodules

    def test_forces_and_restores_all_pynput_backend_overrides(self) -> None:
        observed: list[dict[str, str | None]] = []
        original = {
            "PYNPUT_BACKEND": "xorg",
            "PYNPUT_BACKEND_KEYBOARD": "uinput",
        }
        with mock.patch.dict(os.environ, original, clear=True):
            modules = linux_hotkey_packaging.collect_linux_hotkey_modules(
                self._collector(observed=observed)
            )
            self.assertEqual(os.environ["PYNPUT_BACKEND"], "xorg")
            self.assertEqual(os.environ["PYNPUT_BACKEND_KEYBOARD"], "uinput")
            self.assertNotIn("PYNPUT_BACKEND_MOUSE", os.environ)

        self.assertSetEqual(set(modules), set(EXPECTED_REQUIRED_MODULES))
        self.assertEqual(
            observed,
            [
                {name: "dummy" for name in PYNPUT_BACKEND_ENV_VARS},
                {name: "dummy" for name in PYNPUT_BACKEND_ENV_VARS},
            ],
        )

    def test_rejects_incomplete_collector_result(self) -> None:
        missing_module = "Xlib.ext.record"
        with self.assertRaisesRegex(RuntimeError, re.escape(missing_module)):
            linux_hotkey_packaging.collect_linux_hotkey_modules(
                self._collector(missing=missing_module)
            )

    def test_restores_backend_overrides_when_collection_raises(self) -> None:
        def failing_collector(_package: str, *, on_error: str) -> list[str]:
            self.assertEqual(on_error, "raise")
            raise RuntimeError("collector failed")

        original = {
            "PYNPUT_BACKEND": "xorg",
            "PYNPUT_BACKEND_MOUSE": "uinput",
        }
        with mock.patch.dict(os.environ, original, clear=True):
            with self.assertRaisesRegex(RuntimeError, "collector failed"):
                linux_hotkey_packaging.collect_linux_hotkey_modules(failing_collector)
            self.assertEqual(os.environ["PYNPUT_BACKEND"], "xorg")
            self.assertNotIn("PYNPUT_BACKEND_KEYBOARD", os.environ)
            self.assertEqual(os.environ["PYNPUT_BACKEND_MOUSE"], "uinput")


class LinuxHotkeyArchiveVerifierTests(unittest.TestCase):
    @staticmethod
    def _run_verifier(modules) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFIER)],
            input="\n".join(f" {module}" for module in modules),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_accepts_complete_xorg_hotkey_archive_listing(self) -> None:
        result = self._run_verifier(EXPECTED_REQUIRED_MODULES)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_each_missing_required_module(self) -> None:
        for missing_module in EXPECTED_REQUIRED_MODULES:
            with self.subTest(missing_module=missing_module):
                self.assertEqual(
                    linux_hotkey_packaging.missing_hotkey_modules(
                        EXPECTED_REQUIRED_MODULES - {missing_module}
                    ),
                    [missing_module],
                )

    def test_cli_reports_missing_module(self) -> None:
        result = self._run_verifier(EXPECTED_REQUIRED_MODULES - {"Xlib.ext.record"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("Xlib.ext.record", result.stderr)


if __name__ == "__main__":
    unittest.main()
