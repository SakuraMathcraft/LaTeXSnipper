from __future__ import annotations

from ui.settings_mathcraft_mixin import SettingsMathCraftMixin


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
        )
        is True
    )
    assert harness.result == (
        "🟢 GPU 模式: NVIDIA GeForce RTX 4050 Laptop GPU",
        "gpu",
    )
