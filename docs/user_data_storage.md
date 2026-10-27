# User Data Storage Map

This document tracks where LaTeXSnipper writes user data, runtime state, caches,
and temporary files. Desktop application state uses the shared helpers in
`src/runtime/app_paths.py`; packaged model weights belong to the installation.

## Shared Roots

| Category | Windows | Linux | macOS |
|---|---|---|---|
| App state | `%USERPROFILE%\.latexsnipper` | `~/.latexsnipper` | `~/Library/Application Support/LaTeXSnipper` |
| App logs | `%USERPROFILE%\.latexsnipper\logs` | `~/.latexsnipper/logs` | `~/Library/Logs/LaTeXSnipper` |
| App cache | `%USERPROFILE%\.latexsnipper\cache` | `~/.latexsnipper/cache` | `~/Library/Caches/LaTeXSnipper` |
| App temp | `%TEMP%\LaTeXSnipper` | `$TMPDIR/LaTeXSnipper` or `/tmp/LaTeXSnipper` | `$TMPDIR/LaTeXSnipper` |

## Persistent App State

Application diagnostics use Python's standard `logging` API. `app.log` stores
`INFO` and higher levels as `[date time] [LEVEL] message` with bounded rotation.
`runtime-session.log` is reset after the instance lock is acquired and includes
application `DEBUG` diagnostics as `[LEVEL] message`. It also captures raw
third-party stdout/stderr. The runtime log window only reads this session file;
opening or closing the window does not activate or stop logging.

| Data | Path under app state | Owner |
|---|---|---|
| Main settings | `LaTeXSnipper_config.json` | Unified application settings, including recognition preferences, external models, Automation API, theme, export, and window behavior |
| Local secret key | `secret.key` on Linux/macOS; Windows uses DPAPI and does not create this file | `runtime.secret_store`; created when the first persistent secret is encrypted |
| Automation API discovery | `automation-api.json` | Ephemeral local address and per-session token; created only while the API runs and removed on shutdown |
| Recognition history | `history.json` | Main window history |
| Favorites | `favorites.json` | Favorites window |
| Single-instance lock | `instance.lock` | Runtime single-instance guard |

| Data | Path under app cache | Owner |
|---|---|---|
| Business package downloads | `components/<content-identity>/payload` and `payload.part` | Length and SHA256 checked; complete downloads removed after consumption, interrupted downloads retained for up to seven days since their last use |
| Update staging | `component-update-*` | Private verified business-package staging; removed on failure, cancellation, close or completed deployment; abandoned directories older than one day are reclaimed after startup |
| Deployment handoff | `deployment-*`, `recovery-*` | Independent helper and unelevated watcher; finished tasks are removed after both helpers exit, with a startup sweep for leftovers |

## Installation Resources

The source app uses the developer-selected Python environment directly.

Installation metadata (`distribution.json`) records the platform, architecture, CPU/GPU edition, business-file identity and fixed `base_id`. Windows installs `application/`, `runtime/`, `inference/` and `models/` under the installation root. Linux owns these through the `latexsnipper`, `latexsnipper-runtime`, `latexsnipper-inference` and `latexsnipper-models` dpkg packages, with metadata at `/var/lib/latexsnipper/distribution.json`.

macOS keeps business files and metadata in `LaTeXSnipper.app/Contents/Resources/desktop`. Its fixed resource directories live in `Contents/Frameworks/LaTeXSnipperBase.bundle/Contents/Resources` within the app. The independent nested signature allows business updates to retain that base without traversing its files.

The business directory owns project code, worker source and translations. The fixed runtime owns Pandoc and MathJax. Business updates replace only business files; changing or restoring the fixed base requires the complete installer. Installation resources are separate from writable user configuration.

Windows/Linux transactions keep a temporary `.deployment/` journal and backup
under the resource root. The signed macOS app keeps transaction state beside
the app in `.<app-name>.deployment/`. A separate lock serializes deployment.
Validated transactions commit installation metadata last, then remove backups.
A cleanup failure leaves a completed transaction for a later cleanup attempt; it
does not undo the committed installation or block normal startup.
Interrupted transactions are recovered before normal launch. These backups are
for the active transaction, not a retained history of application versions.

## Model Weights

Packaged workers read only the installed model component and its
`models.v1.json`, verifying model files against their declared digests. Automatic
model downloads are disabled. Missing or corrupt weights require rerunning
the complete desktop installer; the worker never repairs installed files or
uses an external model cache.

Source desktop workers and the standalone library use the platform default
model cache:
Windows `%APPDATA%/MathCraft/models`, Linux
`${XDG_DATA_HOME:-~/.local/share}/LaTeXSnipper/MathCraft/models`, and macOS
`~/Library/Application Support/LaTeXSnipper/MathCraft/models`. The standalone
library also supports its explicit cache argument and `MATHCRAFT_HOME`;
source desktop workers explicitly use the platform default cache regardless
of that override. Packaged desktop workers do not use this cache.

Business payload downloads use platform/architecture/variant/identity and
validate size and SHA256 before use. Catalog files are released after parsing,
and complete business archives after extraction. Interrupted transfers retain
`.part` files for resume; requesting them renews their seven-day retention.
Startup cleanup runs in the background and removes unused complete downloads,
expired partial downloads and finished deployment tasks. Live helpers and tasks
with an unfinished installation transaction are preserved. Unreferenced staging
and handoff directories older than one day are reclaimed; cleanup failures are
retried on a later startup. Installed components and user-selected outputs are
outside this cleanup scope.

## Temporary Files And Caches

| Data | Path | Cleanup |
|---|---|---|
| External PDF image assets | `<app-temp>/pdf-assets/latest` | Cleaned by the PDF worker after processing |
| Screenshot CLI capture files | System temp files with `latexsnipper_cap_` / `latexsnipper_bg_` prefixes | Deleted immediately after use |
| MathCraft worker input image | System temp PNG | Deleted after each request |
| Automation API jobs | Memory only | Images released after execution; completed results expire by TTL/retention cap and all state is released on exit |

## User-Chosen Output

User exports, saved PDFs, saved TeX, and copied asset folders are written only
to paths selected by the user through save dialogs or explicit path settings.

## Uninstall Cleanup

The platform installer owns removal of installation components. User settings,
history, logs and update caches are separate user data. The shared MathCraft
cache also serves the standalone library and is not an installation component.
Windows uninstall owns the installation components and offers separate app-data
and shared-model-cache cleanup choices. Linux uses dpkg removal/purge of the
four installation packages; macOS removes the app. While installed, Linux provides
`latexsnipper-clean-user-data` with separate app-data and shared-model-cache
options. The repository script `scripts/latexsnipper-clean-user-data.sh` supports
both Linux and macOS; it is not deployed inside the macOS app. On macOS, user
data can also be removed manually using the paths above after quitting the app.
Uninstall leaves user data unless explicitly selected for cleanup.
User-selected export paths and external tool installations remain outside the
resource lifecycle.
