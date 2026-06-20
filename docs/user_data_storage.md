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
| Favorites | `favorites.json` by default, unless the user changes the favorites save path in the favorites window | Favorites window |
| LaTeX settings | `latex_settings.json` | LaTeX renderer settings |
| Single-instance lock | `instance.lock` | Runtime single-instance guard |
| Release cache | `release_etag_cache.json` | Update checker |
| Downloaded update package | `updates/` | Update installer cache; old packages are pruned |

## Dependency Runtime

| Data | Path |
|---|---|
| Linux dependency venv | `~/.latexsnipper/deps/python311` |
| macOS dependency venv | `~/Library/Application Support/LaTeXSnipper/deps/python311` |
| Dependency layer state | `<dependency-root>/.deps_state.json` |
| Bundled Windows dependency runtime | Packaged with the Windows distribution where applicable |

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

## User-Chosen Output

User exports, saved PDFs, saved TeX, and copied asset folders are written only
to paths selected by the user through save dialogs or explicit path settings.

## Uninstall Cleanup

LaTeXSnipper preserves user data by default during uninstall so updates and
reinstalls keep settings, history, dependency environments, and model weights.

| Platform | Cleanup entry |
|---|---|
| Windows | The Inno uninstaller prompts for two explicit choices: remove LaTeXSnipper user data/logs/dependency state/temp files, and remove MathCraft model weights. |
| Linux `.deb` | Package removal does not delete home-directory data. Run `latexsnipper-clean-user-data` before `apt purge` or remove the documented user data roots manually. |
| macOS `.dmg` / `.app.zip` | The app bundle includes `Contents/Resources/Uninstall User Data.command`; the `.dmg` also exposes `Uninstall User Data.command` next to the app. |

Custom `MATHCRAFT_HOME` directories are never deleted automatically because
they may point outside LaTeXSnipper-owned storage.
