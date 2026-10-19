"""Fixed frozen Python/Qt host; business modules are loaded from their owned tree."""

import runpy
import sys
from pathlib import Path

executable = Path(sys.executable).resolve()
root = executable.parent.parent
if sys.platform == "darwin":
    base = next(
        parent
        for parent in executable.parents
        if parent.name == "LaTeXSnipperBase.bundle"
    )
    root = base.parent.parent / "Resources/desktop"
application = root / "application"
sys.dont_write_bytecode = True
sys.path[:0] = [str(application), str(application / "worker")]
runpy.run_path(str(application / "main.py"), run_name="__main__")
