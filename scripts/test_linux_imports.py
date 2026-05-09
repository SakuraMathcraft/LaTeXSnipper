#!/usr/bin/env python3
"""Quick smoke-test for Linux compatibility of LaTeXSnipper."""
import sys, os

# Add project root (parent of scripts/) and src/ to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SRC_DIR)

print("=== Testing Linux imports ===")

# Test 1: qhotkey module (should use Linux version)
try:
    from src.backend.qhotkey import QHotkey
    print(f"[OK] qhotkey imported: {QHotkey.__name__}")
except Exception as e:
    print(f"[FAIL] qhotkey: {e}")

# Test 2: platform registry (should not raise RuntimeError)
try:
    from src.backend.platform.registry import PlatformCapabilityRegistry
    r = PlatformCapabilityRegistry()
    providers = r.create()
    print(f"[OK] registry: hotkey={type(providers.hotkey).__name__}, screenshot={type(providers.screenshot).__name__}, system={type(providers.system).__name__}")
except Exception as e:
    print(f"[FAIL] registry: {e}")

# Test 3: hardware module (should use /proc/meminfo)
try:
    from mathcraft_ocr.hardware import detect_hardware_info
    hw = detect_hardware_info()
    print(f"[OK] hardware: memory={hw.total_memory_mb}MB total, {hw.free_memory_mb}MB free")
except Exception as e:
    print(f"[FAIL] hardware: {e}")

# Test 4: Single instance lock (fcntl path)
try:
    import fcntl
    lock_dir = os.path.join(os.path.expanduser("~"), ".latexsnipper")
    os.makedirs(lock_dir, exist_ok=True)
    lock_file = os.path.join(lock_dir, "test.lock")
    fh = open(lock_file, "a+")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    fh.close()
    os.remove(lock_file)
    print("[OK] fcntl file lock works")
except Exception as e:
    print(f"[FAIL] fcntl: {e}")

# Test 5: Verify sys.platform
print(f"[INFO] sys.platform = {sys.platform}")
print(f"[INFO] os.name = {os.name}")

print("=== All tests done ===")
