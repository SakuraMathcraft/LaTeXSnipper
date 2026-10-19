"""Freeze small maintenance processes separately from Qt and inference."""

from pathlib import Path
import os
import sys

ROOT = Path(SPECPATH).parent
paths = [str(ROOT), str(ROOT / 'src')]
sys.path[:0] = paths
from runtime.product_version import PRODUCT_VERSION, write_windows_version_info

version_info = Path(workpath) / 'version_info.txt'
if os.name == 'nt':
    write_windows_version_info(version_info, PRODUCT_VERSION)
excludes = ['PyQt6', 'qfluentwidgets', 'numpy', 'cv2', 'rapidocr', 'fitz', 'transformers',
            'tokenizers', 'onnxruntime', 'torch', 'lxml', 'PIL', 'shapely', 'pyclipper']
identity = os.environ.get('CODESIGN_IDENTITY')

for entry, name in [('maintenance_main.py', 'updater'), ('launcher_main.py', 'LaTeXSnipper')]:
    analysis = Analysis([str(ROOT / 'src' / entry)], pathex=paths, binaries=[], datas=[],
                        hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=excludes, noarchive=False)
    python = PYZ(analysis.pure)
    EXE(python, analysis.scripts, analysis.binaries, analysis.datas, [], name=name,
        debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
        disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
        codesign_identity=identity, entitlements_file=None,
        version=str(version_info) if os.name == 'nt' else None,
        icon=str(ROOT / 'src/assets/icon.ico') if os.name == 'nt' else None)
