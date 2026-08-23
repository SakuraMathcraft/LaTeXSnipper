"""Validation helpers for explicitly selected encrypted tunnel interfaces."""

from __future__ import annotations

import ipaddress
import socket


_TUNNEL_NAME_MARKERS = (
    "tailscale",
    "wireguard",
    "zerotier",
    "hamachi",
    "vpn",
    "tunnel",
    "utun",
    "tun",
    "wg",
)
def tunnel_interface_for_address(address: str) -> str | None:
    bind_ip = ipaddress.ip_address(address.split("%", 1)[0])
    try:
        import psutil

        interfaces = psutil.net_if_addrs()
    except Exception:
        return None
    for interface_name, addresses in interfaces.items():
        normalized_name = interface_name.casefold().replace(" ", "")
        if not any(marker in normalized_name for marker in _TUNNEL_NAME_MARKERS):
            continue
        for item in addresses:
            if item.family not in {socket.AF_INET, socket.AF_INET6}:
                continue
            candidate = str(item.address or "").split("%", 1)[0]
            try:
                if ipaddress.ip_address(candidate) == bind_ip:
                    return interface_name
            except ValueError:
                continue
    return None
