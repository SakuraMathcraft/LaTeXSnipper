"""Fixed frozen Python/Qt host; Python loads the owned business bytecode archive."""

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
sys.path[:0] = [str(application / "application.pyz"), str(application / "worker")]
runpy.run_module("main", run_name="__main__")
