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

`install_base_dir` in `LaTeXSnipper_config.json` is the active dependency root.
Users can change it from the dependency wizard or settings. Each selected root
is also appended to the internal `install_base_dir_cleanup_roots` history so a
later uninstall can clean dependency roots that were used before the final
active one.

Pandoc and Argos translation are not fixed to the application install
directory. They follow the active dependency root:

- Windows packaged builds initially set the dependency root to
  `<install-dir>\_internal\deps` because the installer ships the normalized
  Python template there. In that default state, Pandoc and Argos are created
  below the install tree as `<install-dir>\_internal\deps\pandoc` and
  `<install-dir>\_internal\deps\translation_env`.
- If the user changes the dependency directory, all platforms create Pandoc and
  Argos directly under that selected root instead.
- Linux and macOS packages do not bundle the Windows template. Their default
  dependency roots are user-writable support directories, so Pandoc and Argos
  are created there unless the user selects another root.

| Data | Windows | Linux | macOS | Cleanup owner |
|---|---|---|---|---|
| Bundled Windows Python template | `<install-dir>\_internal\deps\python311` | Not bundled | Not bundled | Windows uninstaller removes installed `_internal` unconditionally |
| Active dependency Python | `<dependency-root>\python311` or another reusable venv name under the selected root | `<dependency-root>/python311` | `<dependency-root>/python311` | Windows dependency cleanup checkbox; Linux/macOS `latexsnipper-clean-user-data --deps` |
| Default packaged dependency root | Windows starts with installed `_internal\deps` for the bundled Python template; switching the dependency path records the new selected root | `~/.latexsnipper/deps` | `~/Library/Application Support/LaTeXSnipper/deps` | Same as above |
| Dependency layer state | `<dependency-root>\.deps_state.json` | `<dependency-root>/.deps_state.json` | `<dependency-root>/.deps_state.json` | Same as above |
| Dependency-managed Pandoc binary | `<dependency-root>\pandoc` | `<dependency-root>/pandoc` | `<dependency-root>/pandoc` | Same as above |
| Argos translation environment | `<dependency-root>\translation_env` | `<dependency-root>/translation_env` | `<dependency-root>/translation_env` | Same as above |

Dependency cleanup deliberately removes only known LaTeXSnipper-managed children
inside every recorded dependency root: `.deps_state.json`, `python311`,
`Python311`, `python_full`, `venv`, `.venv`, `pandoc`, and `translation_env`.
It removes the dependency root itself only if that directory becomes empty. This
is important when a user chooses a broad folder such as `D:\deps` or `~/deps`.
`pandoc` and `translation_env` are direct children of the selected dependency
root; they are not created under an extra nested `deps` directory.

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
| App state root | First config/state access | Contains settings, history, dependency root history, locks, and update cache |
| App log root | Runtime logging/preflight starts | Windows can fall back to `%LOCALAPPDATA%\LaTeXSnipper\logs` if the profile log path is unavailable |
| App temp root | Preview, PDF asset, or launcher helpers run | Grouped under `LaTeXSnipper` in the OS temp directory |
| Dependency root | Dependency bootstrap or user path switch | Can be changed repeatedly; all selected roots are tracked for cleanup |
| `<dependency-root>/python311` | Dependency Python/venv creation | Windows bundled runtime lives under installed `_internal\deps\python311` unless the user switches roots |
| `<dependency-root>/pandoc` | Pandoc layer install | Direct child of the selected dependency root; only created when the optional Pandoc layer is installed |
| `<dependency-root>/translation_env` | Argos local translation deployment | Direct child of the selected dependency root; same root policy as Pandoc |
| MathCraft model cache | MathCraft OCR model download/use | `MATHCRAFT_HOME` can intentionally redirect this outside standard roots |

## User-Chosen Output

User exports, saved PDFs, saved TeX, and copied asset folders are written only
to paths selected by the user through save dialogs or explicit path settings.

## Uninstall Cleanup

LaTeXSnipper preserves user data by default during uninstall so updates and
reinstalls keep settings, history, dependency environments, and model weights.

| Platform | Cleanup entry |
|---|---|
| Windows | The Inno uninstaller removes installed files and `_internal` as install payload. Before uninstall starts it prompts for three optional cleanup choices: app data/logs/temp, dependency environments, and MathCraft model weights. Dependency cleanup reads both the active `install_base_dir` and the `install_base_dir_cleanup_roots` history, then removes only the known managed children from each recorded root. |
| Linux `.deb` | Package removal does not delete home-directory data. Run `latexsnipper-clean-user-data --deps` and any other needed cleanup options before `apt purge`, or remove the documented user data roots manually. The script reads the active dependency root and cleanup history from the app config. |
| macOS `.dmg` / `.app.zip` | The app bundle includes `Contents/Resources/Uninstall User Data.command`; the `.dmg` also exposes `Uninstall User Data.command` next to the app. The script follows the same current-user cleanup policy as Linux. |

Custom `MATHCRAFT_HOME` directories are never deleted automatically because
they may point outside LaTeXSnipper-owned storage. Dependency tools created by
LaTeXSnipper are grouped under the configured dependency root.
