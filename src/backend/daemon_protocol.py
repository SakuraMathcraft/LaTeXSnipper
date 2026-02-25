import json
import socket
from typing import Any


DEFAULT_HOST = "127.0.0.1"


def find_free_port(host: str = DEFAULT_HOST) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        s.listen(1)
        return int(s.getsockname()[1])


def send_line(sock: socket.socket, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False) + "\n"
    sock.sendall(data.encode("utf-8", errors="replace"))


def recv_line(sock: socket.socket, max_bytes: int = 8 * 1024 * 1024) -> dict[str, Any]:
    buf = bytearray()
    while True:
        b = sock.recv(1)
        if not b:
            break
        if b == b"\n":
            break
        buf.extend(b)
        if len(buf) > max_bytes:
            raise RuntimeError("daemon response too large")
    if not buf:
        raise RuntimeError("empty daemon response")
    text = bytes(buf).decode("utf-8", errors="replace").strip()
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise RuntimeError("invalid daemon response type")
    return obj

