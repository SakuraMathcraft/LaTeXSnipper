"""AutoKey workflow for clipboard image data and copied image-file paths."""

import os
import subprocess


PYTHON = "/usr/bin/python3"
CLIENT = "/absolute/path/to/examples/automation/local_client.py"
BACKEND = "mathcraft"
MODE = "formula"


clipboard_api = globals().get("clipboard")
dialog_api = globals().get("dialog")
if clipboard_api is None or dialog_api is None:
    raise RuntimeError("Run this file inside AutoKey.")

clipboard_text = clipboard_api.get_clipboard().strip().strip('"')
source_args = [clipboard_text] if os.path.isfile(clipboard_text) else ["--clipboard"]
command = [
    PYTHON,
    CLIENT,
    *source_args,
    "--backend",
    BACKEND,
    "--mode",
    MODE,
    "--output",
    "text",
    "--copy",
]

try:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
except (OSError, subprocess.TimeoutExpired) as exc:
    dialog_api.info_dialog(
        "LaTeXSnipper", f"Could not run Automation API client:\n{exc}"
    )
else:
    if completed.returncode == 0:
        dialog_api.info_dialog("LaTeXSnipper", "Recognition copied to the clipboard.")
    else:
        detail = (completed.stderr or completed.stdout or "Recognition failed.").strip()
        dialog_api.info_dialog("LaTeXSnipper", detail)
