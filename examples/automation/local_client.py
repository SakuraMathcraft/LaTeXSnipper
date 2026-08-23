"""Submit one local image using LaTeXSnipper's private discovery file."""

from __future__ import annotations

import json
import sys
import urllib.request
import uuid
from pathlib import Path


def connection_file() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LaTeXSnipper" / "automation-api.json"
    return Path.home() / ".latexsnipper" / "automation-api.json"


def main(image_path: str, backend: str = "mathcraft") -> None:
    connection = json.loads(connection_file().read_text(encoding="utf-8"))
    boundary = uuid.uuid4().hex
    image = Path(image_path).read_bytes()
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"backend\"\r\n\r\n{backend}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"mode\"\r\n\r\nformula\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"images\"; filename=\"{Path(image_path).name}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + image + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        connection["base_url"] + "/api/v1/recognition/jobs",
        data=body,
        headers={
            "Authorization": "Bearer " + connection["token"],
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Prefer": "wait=30",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        print(json.dumps(json.load(response), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "mathcraft")
