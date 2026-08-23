"""AutoKey script: recognize an image path currently stored in the clipboard."""

import subprocess

clipboard_api = globals().get("clipboard")
if clipboard_api is None:
    raise RuntimeError("Run this file inside AutoKey.")
image_path = clipboard_api.get_clipboard().strip()
subprocess.Popen(["python3", "/path/to/examples/automation/local_client.py", image_path])
