from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from runtime.main_preflight import pre_bootstrap_runtime  # noqa: E402

pre_bootstrap_runtime()

from runtime.app_runner import run_application  # noqa: E402
from runtime.main_bootstrap import bootstrap_application  # noqa: E402
from runtime.runtime_logging import init_app_logging, open_debug_console  # noqa: E402
from runtime.startup_splash import ensure_startup_splash, startup_status_message  # noqa: E402
from runtime.std_streams import ensure_std_streams  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    bootstrap_application()
    ensure_std_streams()
    ensure_startup_splash(startup_status_message("初始化日志..."))
    init_app_logging()
    ensure_startup_splash(startup_status_message("检查日志窗口设置..."))
    open_debug_console(force=False, tee=True)
    return run_application(MainWindow)


if __name__ == "__main__":
    raise SystemExit(main())
