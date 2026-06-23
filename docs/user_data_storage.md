# User Data Storage Map

This document tracks where LaTeXSnipper writes user data, runtime state, caches,
and temporary files. Keep new app-managed writes under the shared helpers in
`src/runtime/app_paths.py`.

## Shared Roots

| Category | Windows | Linux | macOS |
|---|---|---|---|
| App state | `%USERPROFILE%\.latexsnipper` | `~/.latexsnipper` | `~/Library/Application Support/LaTeXSnipper` |
| App logs | `%USERPROFILE%\.latexsnipper\logs`, with `%LOCALAPPDATA%\LaTeXSnipper\logs` as a fallback | `~/.latexsnipper/logs` | `~/Library/Logs/LaTeXSnipper` |
| App temp | `%TEMP%\LaTeXSnipper` | `$TMPDIR/LaTeXSnipper` or `/tmp/LaTeXSnipper` | `$TMPDIR/LaTeXSnipper` |

## Persistent App State

| Data | Path under app state | Owner |
|---|---|---|
| Main settings | `LaTeXSnipper_config.json` | `runtime.config_manager`, dependency bootstrap, theme, Pandoc runtime |
| Recognition history | `history.json` | Main window history; no user-facing path selector |
| Favorites | `favorites.json`; user-facing export writes a copy to a chosen folder without changing the app data path | Favorites window |
| LaTeX settings | `latex_settings.json` | LaTeX renderer settings |
| Single-instance lock | `instance.lock` | Runtime single-instance guard |
| Release cache | `release_etag_cache.json` | Update checker |
| Downloaded update package | `updates/` | Update installer cache; old packages are pruned |

## Dependency Runtime

`install_base_dir` in `LaTeXSnipper_config.json` is the active dependency root.
Users can change it from the dependency wizard or settings. LaTeXSnipper records
only the current active root and does not keep a cleanup history of previous
user-selected dependency roots.

Pandoc does not follow the active dependency root. It is an app-managed shared
tool under `<app-state>/tools`, so deploying it once keeps it available after
the user switches Python dependency roots.

| Data | Windows | Linux | macOS | Cleanup owner |
|---|---|---|---|---|
| Bundled Windows Python template | `<install-dir>\_internal\deps\python311` | Not bundled | Not bundled | Windows uninstaller removes installed `_internal` unconditionally |
| Active dependency Python | `<dependency-root>\python311` or another reusable Python/venv selected by the user | `<dependency-root>/python311` or another reusable Python/venv selected by the user | `<dependency-root>/python311` or another reusable Python/venv selected by the user | Not removed automatically after the user changes the dependency root |
| Default packaged dependency root | Windows starts with installed `_internal\deps` for the bundled Python template | `~/.latexsnipper/deps` | `~/Library/Application Support/LaTeXSnipper/deps` | Windows `_internal` is removed by the uninstaller; Linux/macOS default app-state deps are removed only when app data is removed |
| Dependency layer state | `<dependency-root>\.deps_state.json` | `<dependency-root>/.deps_state.json` | `<dependency-root>/.deps_state.json` | Stays with the selected dependency root |
| App-managed Pandoc binary | `%USERPROFILE%\.latexsnipper\tools\pandoc` | `~/.latexsnipper/tools/pandoc` | `~/Library/Application Support/LaTeXSnipper/tools/pandoc` | Dependency cleanup checkbox/script |

Dependency cleanup deliberately avoids user-selected external Python roots.
If a user switches `install_base_dir` to a full Python installation, a venv, or
a broad directory such as `D:\deps` or `~/deps`, uninstall will not delete it.
Shared tools are removed from `<app-state>/tools`, not from dependency roots.

Linux/macOS dependency bootstrap uses system Python `>=3.10,<3.13` only to
create the isolated dependency environment. The packaged app itself does not run
on the user's system Python.

## Model Weights

| Data | Current path |
|---|---|
| MathCraft OCR models on Windows | `%APPDATA%\MathCraft\models` |
| MathCraft OCR models on Linux | `${XDG_DATA_HOME:-~/.local/share}/LaTeXSnipper/MathCraft/models` |
| MathCraft OCR models on macOS | `~/Library/Application Support/LaTeXSnipper/MathCraft/models` |
| Bundled MathCraft models | Packaged under `MathCraft/models` when a distribution includes them |

The MathCraft model cache is owned by `mathcraft_ocr.cache`. The settings UI
opens the same directory that `mathcraft_ocr.cache` resolves. `MATHCRAFT_HOME`
can explicitly override the model root.

## Temporary Files And Caches

| Data | Path | Cleanup |
|---|---|---|
| Document PDF preview build files | `<app-temp>/doc-preview` | Cleared when the preview window is created |
| Poppler SVG preview files | `<app-temp>/poppler-svg` | Cleared between preview sessions |
| External PDF image assets | `<app-temp>/pdf-assets/latest` | Cleaned by the PDF worker after processing |
| Screenshot CLI capture files | System temp files with `latexsnipper_cap_` / `latexsnipper_bg_` prefixes | Deleted immediately after use |
| MathCraft worker input image | System temp PNG | Deleted after each request |
| Settings environment terminal scripts | System temp launcher files/directories | Short-lived helper launchers; currently best-effort OS temp cleanup |

## Directory Creation Summary

| Directory | Created when | Notes |
|---|---|---|
| App state root | First config/state access | Contains settings, history, locks, update cache, and shared tools |
| App log root | Runtime logging/preflight starts | Windows can fall back to `%LOCALAPPDATA%\LaTeXSnipper\logs` if the profile log path is unavailable |
| App temp root | Preview, PDF asset, or launcher helpers run | Grouped under `LaTeXSnipper` in the OS temp directory |
| Dependency root | Dependency bootstrap or user path switch | Can be changed repeatedly; only the current root is stored in config |
| `<dependency-root>/python311` | Dependency Python/venv creation | Windows bundled runtime lives under installed `_internal\deps\python311` unless the user switches roots |
| `<app-state>/tools/pandoc` | Pandoc layer install | Shared app-managed tool; independent from the selected Python dependency root |
| MathCraft model cache | MathCraft OCR model download/use | `MATHCRAFT_HOME` can intentionally redirect this outside standard roots |

## User-Chosen Output

User exports, saved PDFs, saved TeX, and copied asset folders are written only
to paths selected by the user through save dialogs or explicit path settings.

## Uninstall Cleanup

LaTeXSnipper preserves user data by default during uninstall so updates and
reinstalls keep settings, history, user-selected dependency environments, shared
tools, and model weights.

| Platform | Cleanup entry |
|---|---|
| Windows | Before the standard Inno uninstall confirmation, the uninstaller prompts for three optional cleanup choices: app data/logs/temp, app-managed shared tools, and MathCraft model weights. After the standard uninstall confirmation is accepted, it asks Windows/Inno to close LaTeXSnipper, force-closes any remaining `LaTeXSnipper.exe`, then runs selected cleanup before the main install payload is removed. The installed `<install-dir>\_internal` directory is removed unconditionally as part of uninstall. User-selected external Python roots are never read from config or deleted. |
| Linux `.deb` | Package removal does not delete home-directory data. Run `latexsnipper-clean-user-data --deps` and any other needed cleanup options before `apt purge`, or remove the documented user data roots manually. The script removes shared tools under the app state root and does not read or delete `install_base_dir`. |
| macOS `.dmg` / `.app.zip` | Moving the `.app` to Trash removes the app bundle only. The app bundle includes `Contents/Resources/Uninstall User Data.command`; the `.dmg` also exposes `Uninstall User Data.command` next to the app. The script follows the same current-user cleanup policy as Linux. |

Custom `MATHCRAFT_HOME` directories are never deleted automatically because
they may point outside LaTeXSnipper-owned storage. Dependency tools created by
LaTeXSnipper are grouped under `<app-state>/tools`.
