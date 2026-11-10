"""Fixed frozen Python/Qt host; Python loads the owned business bytecode archive."""

import runpy
import sys
from pathlib import Path

executable = Path(sys.executable).resolve()
root = executable.parent.parent
if sys.platform == "darwin":
    contents = executable.parent.parent
    if (
        executable.parent.name == "MacOS"
        and contents.name == "Contents"
        and contents.parent.suffix == ".app"
    ):
        # Main executable of the app bundle, launched by LaunchServices.
        root = contents / "Resources/desktop"
    else:
        # Copy kept in the nested base, started by the deployment bootstrap.
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
