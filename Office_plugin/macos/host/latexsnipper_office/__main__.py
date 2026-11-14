"""Entry point of LaTeXSnipper Office.app.

    LaTeXSnipper Office            setup window: install, status, uninstall
    LaTeXSnipper Office --serve    the host launchd keeps running (no Dock icon)
    LaTeXSnipper Office --install    trust the certificate, register the login agent
    LaTeXSnipper Office --uninstall

The host does not need the LaTeXSnipper desktop app. Only screenshot
recognition talks to it, through the desktop's local Automation API.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from latexsnipper_office import __version__

logger = logging.getLogger(f"latexsnipper.{__name__}")


def serve() -> int:
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
    from PyObjCTools import AppHelper

    from latexsnipper_office.dialogs import NativeFileChooser
    from latexsnipper_office.lifecycle import CertificateNotTrusted, OfficeAddinError
    from latexsnipper_office.lifecycle import serve as start

    app = NSApplication.sharedApplication()
    # A background agent: file panels may appear, but no Dock icon or menu bar.
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    try:
        running = start(
            product_version=__version__, files=NativeFileChooser(), interactive=False
        )
    except CertificateNotTrusted as error:
        logger.error("%s", error)
        # Exit cleanly so launchd does not restart into the same failure.
        return 0
    except OfficeAddinError as error:
        logger.error("%s", error)
        return 1
    logger.info("serving %s", running.server.base_url)

    def stop(*_args) -> None:
        running.server.stop()
        AppHelper.stopEventLoop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    AppHelper.runEventLoop(installInterrupt=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="LaTeXSnipper Office")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--serve", action="store_true", help="run the add-in host")
    mode.add_argument(
        "--install", action="store_true", help="install or repair the add-in"
    )
    mode.add_argument(
        "--uninstall", action="store_true", help="remove the add-in and its data"
    )
    # macOS adds -psn_* when an app is opened from Finder on some systems.
    args, _unknown = parser.parse_known_args(argv)
    # The only logging configuration: launchd sends stderr to host.log.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    if args.serve:
        return serve()
    if args.install:
        from latexsnipper_office.install import install

        install()
        return 0
    if args.uninstall:
        from latexsnipper_office.install import uninstall

        uninstall()
        return 0
    from latexsnipper_office.setup_window import run_setup

    return run_setup()


if __name__ == "__main__":
    sys.exit(main())
