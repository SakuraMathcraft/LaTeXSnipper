from __future__ import annotations

import logging
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _SRC_DIR.parent
for _path in (_ROOT_DIR, _SRC_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

if len(sys.argv) == 3 and sys.argv[1] == "--validate-application":
    import json
    import traceback

    _validation_output = Path(sys.argv[2])
    try:
        from runtime.application_validation import validate_application

        validate_application(_validation_output)
    except Exception:
        logging.getLogger("latexsnipper.runtime.application_validation").exception(
            "Application resource validation failed"
        )
        _validation_output.write_text(
            json.dumps({"error": traceback.format_exc()}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        raise SystemExit(1) from None
    raise SystemExit(0)

if getattr(sys, "frozen", False):
    from runtime.installation_layout import deployment_directory
    from runtime.installed_resources import current_target, installation_root
    from update.deployment_transaction import needs_recovery

    _installation = installation_root(Path(sys.executable))
    if needs_recovery(deployment_directory(_installation, current_target()[0])):
        from runtime.runtime_logging import init_app_logging
        from update.deployment_launch import launch_installed

        init_app_logging()
        launch_installed(_installation)
        raise SystemExit(0)

from runtime.runtime_logging import init_app_logging  # noqa: E402
from runtime.std_streams import ensure_std_streams  # noqa: E402
from ui.controllers.runtime_log import apply_runtime_log_window_preference  # noqa: E402

ensure_std_streams()
init_app_logging()

from runtime.main_preflight import pre_bootstrap_runtime  # noqa: E402

pre_bootstrap_runtime()

from application.app_runner import run_application  # noqa: E402
from application.bootstrap import bootstrap_application  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402

logger = logging.getLogger(f"latexsnipper.{__name__}")


def main() -> int:
    try:
        bootstrap_application()
        apply_runtime_log_window_preference(force=False)
        return run_application(MainWindow)
    except Exception:
        logger.exception("LaTeXSnipper 启动失败")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
