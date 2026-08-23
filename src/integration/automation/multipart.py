"""Bounded streaming parser for the small multipart subset used by the API."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from email.parser import BytesHeaderParser
from email.policy import default
from typing import BinaryIO

from integration.automation.contracts import AutomationApiError


_CHUNK_SIZE = 64 * 1024
_MAX_HEADER_BYTES = 16 * 1024


@dataclass(slots=True)
class MultipartPart:
    name: str
    filename: str | None
    stream: BinaryIO
    size: int

    def close(self) -> None:
        self.stream.close()


class _MultipartBody:
    def __init__(self, source: BinaryIO, length: int) -> None:
        self._source = source
        self._remaining = length
        self._buffer = bytearray()

    def _fill(self, minimum: int = 1) -> bool:
        while len(self._buffer) < minimum and self._remaining > 0:
            chunk = self._source.read(min(_CHUNK_SIZE, self._remaining))
            if not chunk:
                raise AutomationApiError(400, "invalid_request", "请求体不完整。")
            self._remaining -= len(chunk)
            self._buffer.extend(chunk)
        return len(self._buffer) >= minimum

    def readline(self, limit: int) -> bytes:
        while True:
            newline = self._buffer.find(b"\n")
            if newline >= 0:
                end = newline + 1
                if end > limit:
                    raise AutomationApiError(400, "invalid_request", "Multipart 请求头过大。")
                line = bytes(self._buffer[:end])
                del self._buffer[:end]
                return line
            if len(self._buffer) >= limit:
                raise AutomationApiError(400, "invalid_request", "Multipart 请求头过大。")
            if not self._fill(len(self._buffer) + 1):
                line = bytes(self._buffer)
                self._buffer.clear()
                return line

    def read_part(self, delimiter: bytes, target: BinaryIO, limit: int) -> int:
        size = 0
        keep = max(1, len(delimiter) - 1)
        while True:
            position = self._buffer.find(delimiter)
            if position >= 0:
                size = _write_bounded(target, self._buffer[:position], size, limit)
                del self._buffer[: position + len(delimiter)]
                return size
            if len(self._buffer) > keep:
                flush_size = len(self._buffer) - keep
                size = _write_bounded(target, self._buffer[:flush_size], size, limit)
                del self._buffer[:flush_size]
            if not self._fill(len(self._buffer) + 1):
                raise AutomationApiError(400, "invalid_request", "Multipart 请求体不完整。")

    def consume_boundary_suffix(self) -> bool:
        if not self._fill(2):
            raise AutomationApiError(400, "invalid_request", "Multipart 分隔符不完整。")
        suffix = bytes(self._buffer[:2])
        del self._buffer[:2]
        if suffix == b"--":
            if self._fill(2) and self._buffer[:2] == b"\r\n":
                del self._buffer[:2]
            return True
        if suffix != b"\r\n":
            raise AutomationApiError(400, "invalid_request", "Multipart 分隔符格式错误。")
        return False

    def finish(self) -> None:
        self._buffer.clear()
        while self._remaining > 0:
            chunk = self._source.read(min(_CHUNK_SIZE, self._remaining))
            if not chunk:
                raise AutomationApiError(400, "invalid_request", "请求体不完整。")
            self._remaining -= len(chunk)


def _write_bounded(target: BinaryIO, data, current: int, limit: int) -> int:
    new_size = current + len(data)
    if new_size > limit:
        raise AutomationApiError(413, "payload_too_large", "Multipart 字段超过大小限制。")
    target.write(data)
    return new_size


def parse_multipart_stream(
    source: BinaryIO,
    *,
    content_length: int,
    boundary: str,
    image_limit: int,
    max_items: int,
) -> list[MultipartPart]:
    try:
        boundary_bytes = boundary.encode("ascii")
    except UnicodeEncodeError as exc:
        raise AutomationApiError(400, "invalid_request", "Multipart 分隔符无效。") from exc
    if not boundary_bytes or len(boundary_bytes) > 200 or any(ch in boundary_bytes for ch in b"\r\n"):
        raise AutomationApiError(400, "invalid_request", "Multipart 分隔符无效。")

    body = _MultipartBody(source, content_length)
    opening = b"--" + boundary_bytes + b"\r\n"
    if body.readline(len(opening) + 2) != opening:
        raise AutomationApiError(400, "invalid_request", "Multipart 请求体格式错误。")

    delimiter = b"\r\n--" + boundary_bytes
    parts: list[MultipartPart] = []
    image_count = 0
    try:
        while True:
            header_lines: list[bytes] = []
            header_size = 0
            while True:
                line = body.readline(_MAX_HEADER_BYTES + 1)
                header_size += len(line)
                if header_size > _MAX_HEADER_BYTES:
                    raise AutomationApiError(400, "invalid_request", "Multipart 请求头过大。")
                if line == b"\r\n":
                    break
                if not line:
                    raise AutomationApiError(400, "invalid_request", "Multipart 请求头不完整。")
                header_lines.append(line)
            headers = BytesHeaderParser(policy=default).parsebytes(b"".join(header_lines))
            if headers.get_content_disposition() != "form-data":
                raise AutomationApiError(400, "invalid_request", "Multipart 字段格式错误。")
            name = str(headers.get_param("name", header="content-disposition") or "")
            filename_value = headers.get_param("filename", header="content-disposition")
            filename = str(filename_value) if filename_value is not None else None
            if not name:
                raise AutomationApiError(400, "invalid_request", "Multipart 字段缺少名称。")
            if headers.get("Content-Transfer-Encoding"):
                raise AutomationApiError(400, "invalid_request", "不支持该 Multipart 传输编码。")

            if name == "images":
                image_count += 1
                if image_count > max_items:
                    raise AutomationApiError(413, "batch_too_large", "批量图片数量超过限制。")
                part_limit = image_limit
                stream = tempfile.SpooledTemporaryFile(max_size=min(image_limit, 1024 * 1024), mode="w+b")
            else:
                part_limit = 4096
                stream = tempfile.SpooledTemporaryFile(max_size=4096, mode="w+b")
            try:
                size = body.read_part(delimiter, stream, part_limit)
                stream.seek(0)
            except Exception:
                stream.close()
                raise
            parts.append(MultipartPart(name=name, filename=filename, stream=stream, size=size))
            if body.consume_boundary_suffix():
                body.finish()
                return parts
    except Exception:
        for part in parts:
            part.close()
        raise
