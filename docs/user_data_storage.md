# User Data Storage Map

This document tracks where LaTeXSnipper writes user data, runtime state, caches,
and temporary files. Desktop application state uses the shared helpers in
`src/runtime/app_paths.py`; model weights use MathCraft's shared cache resolver.

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
| Component downloads | `components/<content-identity>/payload` and `payload.part` | Component downloader; length and SHA256 checked before reuse, interrupted downloads retained for resume |
| Update staging | `component-update-*` | Update controller; private verified component staging, removed on cancellation/close or after deployment feedback |
| Deployment handoff | `deployment-*`, `recovery-*` | Independent helper and unelevated watcher; request/result files removed after feedback or failed-handoff cleanup |

## Installation Resources

The source app uses the developer-selected Python environment directly.

Installation metadata (`distribution.json`) owns the platform, architecture,
CPU/GPU edition and immutable application/inference/models component identities.
Windows resource lookup uses the installation root with `application/`,
`inference/`, `models/` and `distribution.json`. Linux components are owned by
dpkg under `/usr/lib/latexsnipper`; mutable metadata is stored outside the
package payload at `/var/lib/latexsnipper/distribution.json`. macOS uses
`LaTeXSnipper.app/Contents/Resources/desktop` for the three components and
metadata; the outer signed app is rebuilt and verified as a whole.
These resources are not user configuration or writable dependency environments.
The application component owns `pandoc/` and the worker implementation.

Windows/Linux transactions keep a temporary `.deployment/` journal and backup
under the resource root. The signed macOS app keeps transaction state beside
the app in `.<app-name>.deployment/`. A separate lock serializes deployment.
Validated transactions commit installation metadata last, then remove backups.
A cleanup failure leaves a completed transaction for a later cleanup attempt; it
does not undo the committed installation or block normal startup.
Interrupted transactions are recovered before normal launch. These backups are
for the active transaction, not a retained history of application versions.

## Model Weights And Repair Cache

Packaged workers read the installed model component and its `models.v1.json`.
Every model file is checked against its declared digest. Valid installed models
are preferred. Only when an installed model is missing or fails validation does
the worker check the shared MathCraft default cache. Matching files are reused;
missing, corrupt or outdated cached models are downloaded into that same cache.
The current model manifest's file digests determine whether a cached model is
usable, so cached weights cannot shadow valid installed weights.

The desktop and standalone library share the platform default model cache:
Windows `%APPDATA%/MathCraft/models`, Linux
`${XDG_DATA_HOME:-~/.local/share}/LaTeXSnipper/MathCraft/models`, and macOS
`~/Library/Application Support/LaTeXSnipper/MathCraft/models`. The standalone
library also supports its explicit cache argument and `MATHCRAFT_HOME`;
desktop recognition uses the platform default cache regardless of that override.

Component payload caches use component platform/architecture/variant/identity
and validate size and SHA256 before reuse. Interrupted transfers retain `.part`
files. Update staging is separate from the installed components and is removed
after its task finishes; payload caches remain available for verified reuse.

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
three component packages; macOS removes the app. Linux/macOS also
provide `latexsnipper-clean-user-data.sh` with explicit app-data and model-cache
options. Uninstall leaves user data unless explicitly selected for cleanup.
User-selected export paths and external tool installations remain outside the
resource lifecycle.
