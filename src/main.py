from __future__ import annotations

import logging
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent
for _path in (_ROOT_DIR, _SRC_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from runtime.runtime_logging import init_app_logging  # noqa: E402
from ui.runtime_log_controller import apply_runtime_log_window_preference  # noqa: E402
from runtime.std_streams import ensure_std_streams  # noqa: E402

ensure_std_streams()
init_app_logging()

from runtime.main_preflight import pre_bootstrap_runtime  # noqa: E402

pre_bootstrap_runtime()

from application.app_runner import run_application  # noqa: E402
from application.bootstrap import bootstrap_application  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    try:
        bootstrap_application()
        apply_runtime_log_window_preference(force=False, tee=True)
        return run_application(MainWindow)
    except Exception:
        logging.exception("LaTeXSnipper 启动失败")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
