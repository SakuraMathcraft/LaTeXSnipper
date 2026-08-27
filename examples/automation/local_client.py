"""Production-style Automation API client for local discovery and remote uploads."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


TERMINAL_STATES = {"completed", "failed", "canceled"}
CLIPBOARD_MIME_TYPES = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "image/gif",
)


class ClientError(RuntimeError):
    """An actionable client, transport, or API error."""


@dataclass(frozen=True, slots=True)
class ImagePayload:
    filename: str
    content_type: str
    data: bytes


def connection_file() -> Path:
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "LaTeXSnipper"
            / "automation-api.json"
        )
    return Path.home() / ".latexsnipper" / "automation-api.json"


def _validated_connection(
    payload: object, *, source: Path | None = None
) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ClientError("Automation API connection data must be a JSON object.")
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    token = str(payload.get("token") or "").strip()
    parsed = urllib.parse.urlparse(base_url)
    location = f" in {source}" if source else ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ClientError(f"Automation API base_url{location} is invalid.")
    if not token:
        raise ClientError(f"Automation API token{location} is missing.")
    api_version = str(payload.get("api_version") or "1")
    if api_version != "1":
        raise ClientError(f"Unsupported Automation API version: {api_version}")
    return {"base_url": base_url, "token": token}


def load_connection(
    *, path: Path | None = None, base_url: str = "", token: str = ""
) -> dict[str, str]:
    if base_url or token:
        if not base_url or not token:
            raise ClientError("--base-url and --token must be provided together.")
        return _validated_connection({"base_url": base_url, "token": token})
    target = path or connection_file()
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ClientError(
            f"Connection file not found: {target}. Enable 自动化接口 in LaTeXSnipper settings."
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ClientError(f"Cannot read connection file {target}: {exc}") from exc
    return _validated_connection(payload, source=target)


def _content_type(data: bytes, filename: str) -> str:
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"BM", "image/bmp"),
        (b"II*\x00", "image/tiff"),
        (b"MM\x00*", "image/tiff"),
    )
    for signature, mime_type in signatures:
        if data.startswith(signature):
            return mime_type
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    guessed, _encoding = mimetypes.guess_type(filename)
    return (
        guessed
        if guessed and guessed.startswith("image/")
        else "application/octet-stream"
    )


def image_from_path(path_value: str | Path) -> ImagePayload:
    path = Path(path_value).expanduser()
    if not path.is_file():
        raise ClientError(f"Image file does not exist: {path}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ClientError(f"Cannot read image file {path}: {exc}") from exc
    if not data:
        raise ClientError(f"Image file is empty: {path}")
    return ImagePayload(path.name, _content_type(data, path.name), data)


def image_from_stdin(filename: str) -> ImagePayload:
    data = sys.stdin.buffer.read()
    if not data:
        raise ClientError("Standard input did not contain image data.")
    safe_name = Path(filename or "stdin.png").name
    return ImagePayload(safe_name, _content_type(data, safe_name), data)


def _clipboard_command(command: Sequence[str], *, text: bool = False) -> bytes | str:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=text, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClientError(
            f"Clipboard command failed: {' '.join(command)}: {exc}"
        ) from exc
    if completed.returncode != 0:
        stderr = (
            completed.stderr.strip()
            if text
            else completed.stderr.decode(errors="replace").strip()
        )
        raise ClientError(
            stderr or f"Clipboard command exited with {completed.returncode}."
        )
    return completed.stdout


def _clipboard_text_path() -> Path | None:
    commands: list[list[str]] = []
    if shutil.which("wl-paste"):
        commands.append(["wl-paste", "--no-newline", "--type", "text/plain"])
    if shutil.which("xclip"):
        commands.append(["xclip", "-selection", "clipboard", "-t", "UTF8_STRING", "-o"])
    for command in commands:
        try:
            raw = str(_clipboard_command(command, text=True)).strip().strip('"')
        except ClientError:
            continue
        if raw.startswith("file://"):
            raw = urllib.parse.unquote(urllib.parse.urlparse(raw).path)
        candidate = Path(raw).expanduser()
        if raw and candidate.is_file():
            return candidate
    return None


def image_from_linux_clipboard() -> ImagePayload:
    if not sys.platform.startswith("linux"):
        raise ClientError(
            "--clipboard is for Linux; use the AutoHotkey or Hammerspoon wrapper elsewhere."
        )
    text_path = _clipboard_text_path()
    if text_path is not None:
        return image_from_path(text_path)

    commands: list[tuple[list[str], list[str]]] = []
    if shutil.which("wl-paste"):
        try:
            targets = str(
                _clipboard_command(["wl-paste", "--list-types"], text=True)
            ).splitlines()
        except ClientError:
            targets = []
        commands.append((targets, ["wl-paste", "--type"]))
    if shutil.which("xclip"):
        try:
            targets = str(
                _clipboard_command(
                    ["xclip", "-selection", "clipboard", "-t", "TARGETS", "-o"],
                    text=True,
                )
            ).splitlines()
        except ClientError:
            targets = []
        commands.append((targets, ["xclip", "-selection", "clipboard", "-t"]))

    for targets, prefix in commands:
        for mime_type in CLIPBOARD_MIME_TYPES:
            if mime_type not in targets:
                continue
            command = [*prefix, mime_type]
            if command[0] == "xclip":
                command.append("-o")
            data = _clipboard_command(command)
            if isinstance(data, bytes) and data:
                extension = mimetypes.guess_extension(mime_type) or ".png"
                return ImagePayload("clipboard" + extension, mime_type, data)
    raise ClientError(
        "Clipboard has no image or existing image path. Install wl-clipboard on Wayland or xclip on X11."
    )


def _multipart(
    images: Sequence[ImagePayload], *, backend: str, mode: str, timeout: float
) -> tuple[bytes, str]:
    boundary = "----LaTeXSnipper" + uuid.uuid4().hex
    body = bytearray()

    def add_field(name: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(value.encode("utf-8"))
        body.extend(b"\r\n")

    add_field("backend", backend)
    add_field("mode", mode)
    add_field("timeout", str(timeout))
    for index, image in enumerate(images):
        filename = (
            Path(image.filename)
            .name.encode("ascii", errors="replace")
            .decode()
            .replace('"', "_")
        )
        filename = filename or f"image-{index + 1}.png"
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            f'Content-Disposition: form-data; name="images"; filename="{filename}"\r\n'.encode()
        )
        body.extend(f"Content-Type: {image.content_type}\r\n\r\n".encode())
        body.extend(image.data)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), boundary


def _api_error(status: int, payload: object, fallback: str) -> ClientError:
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        error = payload["error"]
        code = str(error.get("code") or "http_error")
        message = str(error.get("message") or fallback)
        request_id = str(error.get("request_id") or "")
        suffix = f" (request_id={request_id})" if request_id else ""
        return ClientError(f"HTTP {status} {code}: {message}{suffix}")
    return ClientError(f"HTTP {status}: {fallback}")


def _open_json(
    request: urllib.request.Request, *, timeout: float
) -> tuple[dict[str, Any], str]:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            location = str(response.headers.get("Location") or "")
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        raise _api_error(
            exc.code, payload, str(exc.reason or "request failed")
        ) from exc
    except urllib.error.URLError as exc:
        raise ClientError(
            f"Cannot connect to LaTeXSnipper Automation API: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise ClientError("Automation API request timed out.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClientError(
            f"Automation API returned invalid JSON (HTTP {status})."
        ) from exc
    if not isinstance(payload, dict):
        raise ClientError("Automation API response must be a JSON object.")
    return payload, location


def _request(url: str, token: str, **kwargs: Any) -> urllib.request.Request:
    headers = dict(kwargs.pop("headers", {}))
    headers["Authorization"] = "Bearer " + token
    return urllib.request.Request(url, headers=headers, **kwargs)


def _job(payload: dict[str, Any]) -> dict[str, Any]:
    job = payload.get("job")
    if not isinstance(job, dict):
        raise ClientError("Automation API response did not contain a job object.")
    return job


def wait_for_terminal(
    connection: dict[str, str],
    payload: dict[str, Any],
    location: str,
    *,
    timeout: float,
    interval: float,
) -> dict[str, Any]:
    job = _job(payload)
    if str(job.get("state") or "") in TERMINAL_STATES:
        return payload
    job_id = str(job.get("id") or "")
    if not job_id:
        raise ClientError("Automation API response did not contain a job id.")
    path = location or f"/api/v1/recognition/jobs/{job_id}"
    url = (
        path
        if path.startswith(("http://", "https://"))
        else connection["base_url"] + path
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(interval)
        payload, _location = _open_json(_request(url, connection["token"]), timeout=20)
        if str(_job(payload).get("state") or "") in TERMINAL_STATES:
            return payload
    raise ClientError(
        f"Recognition job {job_id} did not finish within {timeout:g} seconds."
    )


def submit(
    connection: dict[str, str],
    images: Sequence[ImagePayload],
    *,
    backend: str,
    mode: str,
    job_timeout: float,
    prefer_wait: float,
    poll_interval: float,
) -> dict[str, Any]:
    if not 1 <= len(images) <= 16:
        raise ClientError("Provide between one and sixteen images.")
    body, boundary = _multipart(images, backend=backend, mode=mode, timeout=job_timeout)
    request = _request(
        connection["base_url"] + "/api/v1/recognition/jobs",
        connection["token"],
        data=body,
        headers={
            "Content-Type": "multipart/form-data; boundary=" + boundary,
            "Prefer": f"wait={min(prefer_wait, 30):g}",
            "Idempotency-Key": uuid.uuid4().hex,
        },
        method="POST",
    )
    payload, location = _open_json(request, timeout=max(10, min(prefer_wait, 30) + 10))
    return wait_for_terminal(
        connection, payload, location, timeout=job_timeout + 30, interval=poll_interval
    )


def result_text(payload: dict[str, Any], *, allow_partial: bool) -> str:
    job = _job(payload)
    state = str(job.get("state") or "")
    if state != "completed":
        error = job.get("error") if isinstance(job.get("error"), dict) else {}
        detail = str(
            error.get("message") or error.get("code") or state or "unknown state"
        )
        raise ClientError(f"Recognition job did not complete: {detail}")
    items = job.get("items")
    if not isinstance(items, list):
        raise ClientError("Completed recognition job did not contain result items.")
    failed = [
        item
        for item in items
        if isinstance(item, dict) and item.get("state") != "completed"
    ]
    if failed and not allow_partial:
        details = []
        for item in failed:
            error = item.get("error") if isinstance(item.get("error"), dict) else {}
            details.append(
                f"#{item.get('index', '?')} {error.get('code', 'failed')}: {error.get('message', '')}".strip()
            )
        raise ClientError("One or more images failed: " + "; ".join(details))
    texts = [
        str(item.get("text") or "")
        for item in items
        if isinstance(item, dict) and item.get("state") == "completed"
    ]
    if not texts:
        raise ClientError("Recognition completed without text output.")
    return "\n\n".join(texts)


def copy_text(text: str) -> None:
    if sys.platform == "darwin":
        command = ["pbcopy"]
    elif os.name == "nt":
        command = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Console]::InputEncoding=[Text.UTF8Encoding]::new($false); "
            "[Console]::In.ReadToEnd() | Set-Clipboard",
        ]
    elif shutil.which("wl-copy"):
        command = ["wl-copy", "--type", "text/plain;charset=utf-8"]
    elif shutil.which("xclip"):
        command = ["xclip", "-selection", "clipboard", "-in"]
    else:
        raise ClientError("No clipboard writer found; install wl-clipboard or xclip.")
    try:
        completed = subprocess.run(
            command,
            input=text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ClientError(f"Could not copy recognition output: {exc}") from exc
    if completed.returncode != 0:
        raise ClientError(completed.stderr.strip() or "Clipboard writer failed.")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload images to the LaTeXSnipper Automation API."
    )
    parser.add_argument("images", nargs="*", help="one to sixteen image paths")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--clipboard",
        action="store_true",
        help="read image data or a path from the Linux clipboard",
    )
    source.add_argument(
        "--stdin",
        action="store_true",
        help="read encoded image bytes from standard input",
    )
    parser.add_argument(
        "--filename", default="stdin.png", help="filename used with --stdin"
    )
    parser.add_argument(
        "--backend", choices=("mathcraft", "external"), default="mathcraft"
    )
    parser.add_argument(
        "--mode", choices=("formula", "text", "mixed"), default="formula"
    )
    parser.add_argument(
        "--timeout", type=float, default=120, help="server-side recognition timeout"
    )
    parser.add_argument(
        "--prefer-wait",
        type=float,
        default=30,
        help="initial HTTP wait, capped at 30 seconds",
    )
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument(
        "--connection", type=Path, help="override the local discovery file"
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("BASE_URL", ""), help="remote API base URL"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("LATEXSNIPPER_REMOTE_KEY", ""),
        help="remote Bearer key",
    )
    parser.add_argument("--output", choices=("text", "json"), default="text")
    parser.add_argument(
        "--copy", action="store_true", help="copy recognized text to the clipboard"
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="return successful items from a partial batch",
    )
    args = parser.parse_args(argv)
    if args.timeout <= 0 or args.timeout > 3600:
        parser.error("--timeout must be greater than 0 and no more than 3600")
    if args.prefer_wait < 0 or args.poll_interval <= 0:
        parser.error(
            "--prefer-wait cannot be negative and --poll-interval must be positive"
        )
    if not args.images and not args.clipboard and not args.stdin:
        parser.error("provide image paths, --clipboard, or --stdin")
    if args.images and (args.clipboard or args.stdin):
        parser.error("image paths cannot be combined with --clipboard or --stdin")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        connection = load_connection(
            path=args.connection, base_url=args.base_url, token=args.token
        )
        if args.clipboard:
            images = [image_from_linux_clipboard()]
        elif args.stdin:
            images = [image_from_stdin(args.filename)]
        else:
            images = [image_from_path(value) for value in args.images]
        payload = submit(
            connection,
            images,
            backend=args.backend,
            mode=args.mode,
            job_timeout=args.timeout,
            prefer_wait=args.prefer_wait,
            poll_interval=args.poll_interval,
        )
        text = result_text(payload, allow_partial=args.allow_partial)
        if args.copy:
            copy_text(text)
        print(
            json.dumps(payload, ensure_ascii=False, indent=2)
            if args.output == "json"
            else text
        )
        return 0
    except ClientError as exc:
        print(f"LaTeXSnipper Automation API: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("LaTeXSnipper Automation API: canceled by user", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
