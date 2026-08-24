from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from update.installer_launch import _schedule_windows_installer


def test_windows_installer_waiter_does_not_spawn_a_console(tmp_path: Path) -> None:
    installer = tmp_path / "LaTeXSnipperSetup-3.0.0.exe"
    installer.touch()

    with (
        patch("update.installer_launch.tempfile.gettempdir", return_value=str(tmp_path)),
        patch("update.installer_launch.os.getpid", return_value=4321),
        patch("update.installer_launch.subprocess.Popen") as popen,
        patch("update.installer_launch._hidden_subprocess_kwargs", return_value={"creationflags": 1}),
    ):
        _schedule_windows_installer(str(installer))

    script = (tmp_path / "latexsnipper-install-4321.vbs").read_text(encoding="utf-8")
    assert "Win32_Process" in script
    assert "processes.Count = 0" in script
    assert "cmd" not in script.lower()
    assert "tasklist" not in script.lower()
    popen.assert_called_once_with(
        ["wscript.exe", "//B", "//NoLogo", str(tmp_path / "latexsnipper-install-4321.vbs")],
        close_fds=True,
        creationflags=1,
    )
