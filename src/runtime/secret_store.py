from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import os
import sys
from ctypes import wintypes
from pathlib import Path

from runtime.app_paths import app_state_dir


PREFIX_WIN = "dpapi:"
PREFIX_LOCAL = "local:"
LOCAL_KEY_FILE = "secret.key"


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text.encode("ascii"))


def _encrypt_windows(value: str) -> str:
    data = value.encode("utf-8")
    in_buf = ctypes.create_string_buffer(data)
    in_blob = _DataBlob(len(data), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptProtectData failed")
    try:
        protected = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return PREFIX_WIN + _b64e(protected)


def _decrypt_windows(value: str) -> str:
    protected = _b64d(value.removeprefix(PREFIX_WIN))
    in_buf = ctypes.create_string_buffer(protected)
    in_blob = _DataBlob(len(protected), ctypes.cast(in_buf, ctypes.POINTER(ctypes.c_char)))
    out_blob = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        return ""
    try:
        raw = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    return raw.decode("utf-8")


def _local_key_path() -> Path:
    root = app_state_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root / LOCAL_KEY_FILE


def _load_local_key() -> bytes:
    path = _local_key_path()
    if path.exists():
        key = path.read_bytes()
    else:
        key = os.urandom(32)
        path.write_bytes(key)
        try:
            path.chmod(0o600)
        except Exception:
            pass
    return hashlib.sha256(key).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
        counter += 1
    return b"".join(blocks)[:length]


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream, strict=True))


def _encrypt_local(value: str) -> str:
    key = _load_local_key()
    nonce = os.urandom(16)
    plain = value.encode("utf-8")
    cipher = _xor(plain, _keystream(key, nonce, len(plain)))
    tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()[:16]
    return PREFIX_LOCAL + _b64e(nonce + tag + cipher)


def _decrypt_local(value: str) -> str:
    raw = _b64d(value.removeprefix(PREFIX_LOCAL))
    if len(raw) < 32:
        return ""
    nonce, tag, cipher = raw[:16], raw[16:32], raw[32:]
    key = _load_local_key()
    expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(tag, expected):
        return ""
    return _xor(cipher, _keystream(key, nonce, len(cipher))).decode("utf-8")


def encrypt_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if sys.platform == "win32":
        return _encrypt_windows(text)
    return _encrypt_local(text)


def decrypt_secret(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        if text.startswith(PREFIX_WIN) and sys.platform == "win32":
            return _decrypt_windows(text)
        if text.startswith(PREFIX_LOCAL):
            return _decrypt_local(text)
    except Exception:
        return ""
    return ""
