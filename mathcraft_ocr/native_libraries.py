"""Audit the private CUDA runtime actually loaded in the current worker process."""

from pathlib import Path


def audit_private_gpu_libraries(native: Path) -> dict[str, str]:
    import os
    from pathlib import Path

    native = Path(native).resolve()
    native_modules = {}
    paths = []
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel.GetCurrentProcess()
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        psapi.EnumProcessModules.restype = wintypes.BOOL
        psapi.GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        psapi.GetModuleFileNameExW.restype = wintypes.DWORD
        modules = (wintypes.HMODULE * 4096)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcessModules(process, modules, ctypes.sizeof(modules), ctypes.byref(needed)) or needed.value > ctypes.sizeof(modules):
            raise RuntimeError('Cannot inspect GPU runtime module paths')
        for index in range(needed.value // ctypes.sizeof(wintypes.HMODULE)):
            buffer = ctypes.create_unicode_buffer(32768)
            if psapi.GetModuleFileNameExW(process, modules[index], buffer, len(buffer)):
                paths.append(Path(buffer.value))
    else:
        for line in Path('/proc/self/maps').read_text().splitlines():
            parts = line.split(maxsplit=5)
            if len(parts) == 6 and parts[5].startswith('/'):
                paths.append(Path(parts[5]))
    for path in paths:
        name = path.name.lower()
        if name.startswith(('cudart', 'cublas', 'cufft', 'curand', 'cudnn', 'nvrtc', 'nvjitlink', 'libcudart', 'libcublas', 'libcufft', 'libcurand', 'libcudnn', 'libnvrtc', 'libnvjitlink')):
            if not path.resolve().is_relative_to(native.resolve()):
                raise RuntimeError('GPU runtime library loaded outside the component: ' + str(path))
            native_modules[path.name] = str(path.resolve())
    if not native_modules:
        raise RuntimeError('No private GPU runtime libraries were observed')
    return native_modules
