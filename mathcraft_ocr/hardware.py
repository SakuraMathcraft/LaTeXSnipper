# coding: utf-8

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from functools import lru_cache
import json
import os
import subprocess

from .providers import GPU_PROVIDER_NAMES, ProviderInfo


@dataclass(frozen=True)
class HardwareInfo:
    logical_processors: int
    total_memory_mb: int
    free_memory_mb: int
    gpu_name: str = ""
    gpu_total_memory_mb: int = 0
    gpu_free_memory_mb: int = 0
    gpu_driver_version: str = ""


@lru_cache(maxsize=1)
def detect_hardware_info() -> HardwareInfo:
    total_mb, free_mb = _windows_memory_status()
    gpu_name, gpu_total_mb, gpu_free_mb, gpu_driver = _query_nvidia_smi()
    if not gpu_name:
        gpu_name, gpu_total_mb, gpu_driver = _query_windows_video_controller()
    return HardwareInfo(
        logical_processors=max(1, int(os.cpu_count() or 1)),
        total_memory_mb=total_mb,
        free_memory_mb=free_mb,
        gpu_name=gpu_name,
        gpu_total_memory_mb=gpu_total_mb,
        gpu_free_memory_mb=gpu_free_mb,
        gpu_driver_version=gpu_driver,
    )


def choose_rec_batch_num(
    provider_info: ProviderInfo,
    hardware: HardwareInfo | None = None,
) -> int:
    hw = hardware or detect_hardware_info()
    active = str(provider_info.active_provider or "")
    if provider_info.device == "gpu" and active in GPU_PROVIDER_NAMES:
        free_vram = max(0, int(hw.gpu_free_memory_mb or 0))
        if free_vram >= 8192:
            return 24
        if free_vram >= 6144:
            return 16
        if free_vram >= 4096:
            return 12
        if free_vram > 0:
            return 8
        total_vram = max(0, int(hw.gpu_total_memory_mb or 0))
        if total_vram >= 7900:
            return 12
        if total_vram >= 3900:
            return 8
        if total_vram > 0:
            return 6
        return 8

    threads = max(1, int(hw.logical_processors or 1))
    free_ram = max(0, int(hw.free_memory_mb or 0))
    if threads >= 12 and free_ram >= 8192:
        return 8
    if threads >= 8:
        return 6
    return 4


def _query_nvidia_smi() -> tuple[str, int, int, str]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.0,
        )
    except Exception:
        return "", 0, 0, ""
    if proc.returncode != 0:
        return "", 0, 0, ""
    line = next((item.strip() for item in proc.stdout.splitlines() if item.strip()), "")
    parts = [part.strip() for part in line.split(",")]
    if len(parts) < 4:
        return "", 0, 0, ""
    return parts[0], _safe_int(parts[1]), _safe_int(parts[2]), parts[3]


def _query_windows_video_controller() -> tuple[str, int, str]:
    if os.name != "nt":
        return "", 0, ""
    commands = (
        "Get-CimInstance Win32_VideoController | "
        "Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | "
        "Select-Object -First 1 Name,AdapterRAM,DriverVersion | "
        "ConvertTo-Json -Compress",
        "Get-WmiObject Win32_VideoController | "
        "Where-Object {$_.Name -and $_.Name -notmatch 'Microsoft Basic'} | "
        "Select-Object -First 1 Name,AdapterRAM,DriverVersion | "
        "ConvertTo-Json -Compress",
    )
    for command in commands:
        payload = _run_powershell_json(command)
        if payload is None:
            continue
        name, adapter_ram_mb, driver = _parse_video_controller_payload(payload)
        if name:
            return name, adapter_ram_mb, driver
    return "", 0, ""


def _run_powershell_json(command: str) -> object | None:
    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3.0,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _parse_video_controller_payload(payload: object) -> tuple[str, int, str]:
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        return "", 0, ""
    name = str(payload.get("Name") or "").strip()
    driver = str(payload.get("DriverVersion") or "").strip()
    adapter_ram = _safe_int(str(payload.get("AdapterRAM") or "0"))
    adapter_ram_mb = adapter_ram // (1024 * 1024) if adapter_ram > 0 else 0
    return name, adapter_ram_mb, driver


def _windows_memory_status() -> tuple[int, int]:
    if os.name != "nt":
        return 0, 0

    class _MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = _MemoryStatusEx()
    status.dwLength = ctypes.sizeof(_MemoryStatusEx)
    try:
        ok = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    except Exception:
        return 0, 0
    if not ok:
        return 0, 0
    mb = 1024 * 1024
    return int(status.ullTotalPhys // mb), int(status.ullAvailPhys // mb)


def _safe_int(value: str) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return 0
