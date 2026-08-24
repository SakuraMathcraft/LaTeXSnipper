"""Submit one local image using LaTeXSnipper's private discovery file."""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path


def connection_file() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LaTeXSnipper" / "automation-api.json"
    return Path.home() / ".latexsnipper" / "automation-api.json"


TERMINAL_STATES = {"completed", "failed", "canceled"}


def _open_json(request: urllib.request.Request, *, timeout: float) -> tuple[dict, str]:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response), str(response.headers.get("Location") or "")


def _wait_for_terminal(connection: dict, payload: dict, location: str) -> dict:
    job = payload.get("job") or {}
    if job.get("state") in TERMINAL_STATES:
        return payload
    job_id = str(job.get("id") or "")
    if not job_id:
        raise RuntimeError("Automation API response did not contain a job id")
    path = location or f"/api/v1/recognition/jobs/{job_id}"
    url = path if path.startswith(("http://", "https://")) else connection["base_url"] + path
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        time.sleep(0.25)
        request = urllib.request.Request(
            url,
            headers={"Authorization": "Bearer " + connection["token"]},
        )
        payload, _location = _open_json(request, timeout=20)
        if (payload.get("job") or {}).get("state") in TERMINAL_STATES:
            return payload
    raise TimeoutError("Recognition job did not finish within 150 seconds")


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
    payload, location = _open_json(request, timeout=35)
    result = _wait_for_terminal(connection, payload, location)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "mathcraft")
