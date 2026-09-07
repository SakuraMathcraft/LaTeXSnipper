from __future__ import annotations

import os
import sys
from pathlib import Path


import ui.settings_mathcraft_mixin as mathcraft_module
from ui.settings_mathcraft_mixin import SettingsMathCraftMixin


def test_settings_python_resolution_does_not_launch_validation_process(
    tmp_path: Path, monkeypatch
) -> None:
    pyexe = tmp_path / ("python.exe" if os.name == "nt" else "python")
    pyexe.write_bytes(b"")
    monkeypatch.setattr(
        mathcraft_module, "_existing_non_launcher_pyexe_from_env", lambda: ""
    )
    monkeypatch.setattr(
        mathcraft_module, "iter_python_candidates", lambda _base: [pyexe]
    )

    class Harness(SettingsMathCraftMixin):
        def _current_install_base_dir(self):
            return tmp_path

    assert Harness()._resolve_dynamic_main_pyexe() == str(pyexe)


def test_compute_mode_label_uses_mathcraft_device_report() -> None:
    class Harness(SettingsMathCraftMixin):
        def _set_compute_mode_text(self, text: str, state: str) -> None:
            self.result = (text, state)

    harness = Harness()

    assert (
        harness._apply_compute_mode_from_info(
            {
                "present": True,
                "device": "gpu",
                "device_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
                "device_verified": True,
            },
            sys.executable,
        )
        is True
    )
    assert harness.result == (
        "🟢 GPU 模式: NVIDIA GeForce RTX 4050 Laptop GPU",
        "gpu",
    )
