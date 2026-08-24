# coding: utf-8

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import os
import platform
from pathlib import Path
import subprocess
import sys
import uuid


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: int | None = None
    name: str = ""
    uuid: str = ""
    verified: bool = False


@dataclass(frozen=True)
class NvidiaDevice:
    index: int
    name: str
    uuid: str
    total_memory_mb: int = 0
    free_memory_mb: int = 0
    driver_version: str = ""


@dataclass(frozen=True)
class DxgiAdapter:
    index: int
    name: str
    luid: str
    dedicated_memory_mb: int = 0


def resolve_device_identity(provider: str | None, device_id: int | None) -> DeviceIdentity:
    active = str(provider or "")
    if active == "CPUExecutionProvider":
        return DeviceIdentity(name=_cpu_name(), verified=True)
    selected_id = max(0, int(device_id or 0))
    if active in {"CUDAExecutionProvider", "TensorrtExecutionProvider"}:
        device = select_nvidia_device(query_nvidia_devices(), selected_id)
        if device is None:
            return DeviceIdentity(device_id=selected_id)
        return DeviceIdentity(device_id=selected_id, name=device.name, uuid=device.uuid)
    if active == "DmlExecutionProvider":
        adapters = query_dxgi_adapters()
        adapter = next((item for item in adapters if item.index == selected_id), None)
        if adapter is None:
            return DeviceIdentity(device_id=selected_id)
        return DeviceIdentity(device_id=selected_id, name=adapter.name, uuid=adapter.luid)
    return DeviceIdentity()


def confirm_device_identity(provider: str | None, device_id: int | None) -> DeviceIdentity:
    active = str(provider or "")
    selected = resolve_device_identity(active, device_id)
    if active in {"CUDAExecutionProvider", "TensorrtExecutionProvider"}:
        active_uuids = query_nvidia_process_gpu_uuids()
        if not active_uuids:
            return selected
        devices = query_nvidia_devices()
        matches = [item for item in devices if item.uuid.lower() in active_uuids]
        if len(matches) == 1:
            device = matches[0]
            return DeviceIdentity(
                device_id=max(0, int(device_id or 0)),
                name=device.name,
                uuid=device.uuid,
                verified=True,
            )
        if selected.uuid and selected.uuid.lower() in active_uuids:
            return DeviceIdentity(
                device_id=selected.device_id,
                name=selected.name,
                uuid=selected.uuid,
                verified=True,
            )
        return DeviceIdentity(device_id=max(0, int(device_id or 0)))
    if active == "DmlExecutionProvider":
        return DeviceIdentity(
            device_id=selected.device_id,
            name=selected.name,
            uuid=selected.uuid,
            verified=bool(selected.name),
        )
    return selected


def query_nvidia_devices() -> tuple[NvidiaDevice, ...]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,uuid,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3.0,
        )
    except Exception:
        return ()
    if proc.returncode != 0:
        return ()
    devices: list[NvidiaDevice] = []
    for raw in proc.stdout.splitlines():
        parts = [part.strip() for part in raw.split(",")]
        if len(parts) < 6:
            continue
        try:
            index = int(parts[0])
        except (TypeError, ValueError):
            continue
        devices.append(
            NvidiaDevice(
                index=index,
                name=parts[1],
                uuid=parts[2],
                total_memory_mb=_safe_int(parts[3]),
                free_memory_mb=_safe_int(parts[4]),
                driver_version=parts[5],
            )
        )
    return tuple(devices)


def query_nvidia_process_gpu_uuids(pid: int | None = None) -> frozenset[str]:
    expected_pid = int(pid or os.getpid())
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,gpu_uuid",
                "--format=csv,noheader,nounits",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3.0,
        )
    except Exception:
        return frozenset()
    if proc.returncode != 0:
        return frozenset()
    matches: set[str] = set()
    for raw in proc.stdout.splitlines():
        parts = [part.strip() for part in raw.split(",", 1)]
        if len(parts) != 2:
            continue
        try:
            process_id = int(parts[0])
        except (TypeError, ValueError):
            continue
        if process_id == expected_pid and parts[1]:
            matches.add(parts[1].lower())
    return frozenset(matches)


def select_nvidia_device(
    devices: tuple[NvidiaDevice, ...],
    logical_device_id: int,
    visible_devices: str | None = None,
) -> NvidiaDevice | None:
    if logical_device_id < 0:
        return None
    raw_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "") if visible_devices is None else visible_devices
    tokens = [token.strip() for token in raw_visible.split(",") if token.strip()]
    if tokens:
        if logical_device_id >= len(tokens):
            return None
        token = tokens[logical_device_id]
        if token == "-1":
            return None
        if token.isdigit():
            physical_index = int(token)
            return next((item for item in devices if item.index == physical_index), None)
        normalized = token.lower()
        return next(
            (
                item
                for item in devices
                if item.uuid.lower() == normalized or item.uuid.lower().startswith(normalized)
            ),
            None,
        )
    return next((item for item in devices if item.index == logical_device_id), None)


def query_dxgi_adapters() -> tuple[DxgiAdapter, ...]:
    if os.name != "nt":
        return ()
    try:
        return _query_dxgi_adapters_windows()
    except Exception:
        return ()


def _query_dxgi_adapters_windows() -> tuple[DxgiAdapter, ...]:
    from ctypes import wintypes

    class _Guid(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

        @classmethod
        def parse(cls, value: str):
            return cls.from_buffer_copy(uuid.UUID(value).bytes_le)

    class _Luid(ctypes.Structure):
        _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

    class _AdapterDesc1(ctypes.Structure):
        _fields_ = [
            ("Description", ctypes.c_wchar * 128),
            ("VendorId", wintypes.UINT),
            ("DeviceId", wintypes.UINT),
            ("SubSysId", wintypes.UINT),
            ("Revision", wintypes.UINT),
            ("DedicatedVideoMemory", ctypes.c_size_t),
            ("DedicatedSystemMemory", ctypes.c_size_t),
            ("SharedSystemMemory", ctypes.c_size_t),
            ("AdapterLuid", _Luid),
            ("Flags", wintypes.UINT),
        ]

    factory = ctypes.c_void_p()
    create_factory = ctypes.windll.dxgi.CreateDXGIFactory1
    create_factory.argtypes = [ctypes.POINTER(_Guid), ctypes.POINTER(ctypes.c_void_p)]
    create_factory.restype = ctypes.c_long
    iid_factory1 = _Guid.parse("770aae78-f26f-4dba-a829-253c83d1b387")
    result = create_factory(ctypes.byref(iid_factory1), ctypes.byref(factory))
    if result < 0 or not factory.value:
        return ()

    def _method(pointer: ctypes.c_void_p, index: int, prototype):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return prototype(table[index])

    release_proto = ctypes.WINFUNCTYPE(wintypes.ULONG, ctypes.c_void_p)
    enum_proto = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_void_p,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
    )
    get_desc_proto = ctypes.WINFUNCTYPE(
        ctypes.c_long,
        ctypes.c_void_p,
        ctypes.POINTER(_AdapterDesc1),
    )
    release_factory = _method(factory, 2, release_proto)
    enum_adapters = _method(factory, 12, enum_proto)
    adapters: list[DxgiAdapter] = []
    try:
        index = 0
        while True:
            adapter = ctypes.c_void_p()
            result = enum_adapters(factory, index, ctypes.byref(adapter))
            if result != 0 or not adapter.value:
                break
            release_adapter = _method(adapter, 2, release_proto)
            try:
                desc = _AdapterDesc1()
                get_desc = _method(adapter, 10, get_desc_proto)
                if get_desc(adapter, ctypes.byref(desc)) >= 0:
                    high = int(desc.AdapterLuid.HighPart) & 0xFFFFFFFF
                    low = int(desc.AdapterLuid.LowPart) & 0xFFFFFFFF
                    adapters.append(
                        DxgiAdapter(
                            index=index,
                            name=str(desc.Description).strip(),
                            luid=f"LUID-{high:08X}-{low:08X}",
                            dedicated_memory_mb=int(desc.DedicatedVideoMemory // (1024 * 1024)),
                        )
                    )
            finally:
                release_adapter(adapter)
            index += 1
    finally:
        release_factory(factory)
    return tuple(adapters)


def _cpu_name() -> str:
    if os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            name = str(value or "").strip()
            if name:
                return name
        except Exception:
            pass
    name = str(platform.processor() or "").strip()
    if name:
        return name
    if os.name == "nt":
        return str(os.environ.get("PROCESSOR_IDENTIFIER", "") or "").strip()
    if sys.platform == "darwin":
        try:
            proc = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=2.0,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
        except Exception:
            return ""
    try:
        for raw in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore").splitlines():
            if raw.lower().startswith("model name"):
                return raw.split(":", 1)[-1].strip()
    except Exception:
        pass
    return ""


def _safe_int(value: str) -> int:
    try:
        return int(float(str(value).strip().replace(",", "")))
    except Exception:
        return 0


__all__ = [
    "DeviceIdentity",
    "DxgiAdapter",
    "NvidiaDevice",
    "confirm_device_identity",
    "query_dxgi_adapters",
    "query_nvidia_devices",
    "query_nvidia_process_gpu_uuids",
    "resolve_device_identity",
    "select_nvidia_device",
]
