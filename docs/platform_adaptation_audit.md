# Platform Adaptation Audit

This document tracks known Windows/Linux/macOS client adaptation gaps. Keep it
as a working checklist: when a platform cleanup PR fixes an item, update the
status and link the relevant code or test evidence.

## Status Legend

- `open`: known issue, not fixed yet.
- `in progress`: active cleanup work exists.
- `fixed`: implementation was updated and verified.
- `accepted`: intentionally platform-specific behavior.

## Current Findings

| Status | Area | Files | Issue | Impact | Cleanup Direction |
|---|---|---|---|---|---|
| fixed | Settings terminal launcher | `src/ui/settings_environment_mixin.py` | The "Open environment terminal" action was Windows-only: it wrote a `.bat`, launched `cmd.exe /k`, used `doskey`, prepended `Scripts`, and joined `PATH` with `;`. | Linux/macOS users saw a settings action that could not open the app-managed dependency environment correctly. | Windows keeps the `.bat`/`cmd.exe` path. Linux/macOS now generate a POSIX launcher, prepend a wrapper directory for `python`, `py`, and `pip`, and open it through macOS `open` or common Linux terminal emulators. Verified with `python -m compileall -q src\ui\settings_environment_mixin.py src\ui\settings_mathcraft_mixin.py`. |
| fixed | Startup Python resolver | `src/bootstrap/deps_python_runtime.py`, `src/runtime/python_runtime_resolver.py`, `src/runtime/main_bootstrap.py` | `ensure_full_python_or_prompt()` had a non-frozen fallback that only searched `python3.11.exe`, `python.exe`, and `python3.exe`. | Linux/macOS source-mode or non-packaged startup could fail to discover system `python3`; overly new system Python versions could also be selected before dependency compatibility was verified. | Linux/macOS now use the shared `find_system_python3()` path with supported system Python `>=3.10,<3.13`, preferring 3.11. Windows-only `.exe` installer lookup remains guarded by `os.name == "nt"`. Verified with `python -m compileall -q src\bootstrap\deps_python_runtime.py src\runtime\python_runtime_resolver.py src\bootstrap\deps_entry.py`. |
| fixed | Device-name probing in settings | `src/ui/settings_mathcraft_mixin.py` | Local device probing called PowerShell/WMI first and only fell back to `nvidia-smi` for GPU. | On Linux/macOS CPU/GPU labels could be empty or misleading. The failure was swallowed, but the UI adaptation was incomplete. | Device probing now branches by platform: Windows uses PowerShell/WMI with `nvidia-smi` fallback; macOS uses `sysctl` and `system_profiler`; Linux uses `nvidia-smi`, `lspci`, `lscpu`, and `/proc/cpuinfo` where available. Verified with `python -m compileall -q src\ui\settings_environment_mixin.py src\ui\settings_mathcraft_mixin.py`. |
| fixed | MathCraft hardware sizing | `mathcraft_ocr/hardware.py`, `test/test_mathcraft_ocr.py`, `pyproject.toml`, `mathcraft_ocr/__init__.py` | Memory detection used Windows `GlobalMemoryStatusEx`; non-Windows returned `(0, 0)`. GPU detection was mostly NVIDIA-oriented, with Windows WMI as fallback. | CPU batch sizing on Linux/macOS fell back to conservative defaults and could not use available RAM information. | Memory detection now uses `psutil.virtual_memory()` when available, Windows API on Windows, POSIX `sysconf` on Linux/macOS, and macOS `vm_stat` to fill available memory when needed. `nvidia-smi` remains optional. Covered by focused hardware tests and released as `mathcraft-ocr` 0.2.3. |
| fixed | User-facing mojibake / dependency log boxes | `src/bootstrap/*`, `src/backend/cuda_runtime_policy.py`, `src/ui/settings_mathcraft_mixin.py` | Dependency install logs and CUDA/cuDNN diagnostics could decode subprocess output with the platform default encoding, and dependency-window status text used emoji markers that can render as square boxes on some Qt/Windows fonts. Earlier source-file mojibake reports were verified as console display issues by reading source as UTF-8. | Dependency installation, Pandoc checks, package verification, CUDA version detection, and local device probes could show garbled text or missing-glyph boxes in the dependency UI. | Subprocess log paths now set `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, `encoding="utf-8"`, and `errors="replace"` where output is captured. Dependency-window emoji markers were replaced with ASCII prefixes such as `[OK]`, `[WARN]`, `[ERR]`, and `[HINT]`. Verified with `python -m compileall -q` on the touched modules and a bootstrap emoji scan. |
| fixed | Non-Windows PATH cleanup | `src/runtime/python_runtime_resolver.py` | `_scrub_path_inplace()` split `PATH` with `;`, which is Windows-specific. It is called in relaunch code that can run on Linux/macOS. | Non-Windows relaunch could collapse PATH into a single malformed entry if this path was reached. | `_scrub_path_inplace()` now uses `os.pathsep` for splitting and joining. Windows Store Python alias filtering is applied only on Windows. Verified with `python -m compileall -q src\runtime\python_runtime_resolver.py`. |
| fixed | Application-managed write paths on macOS | `src/runtime/app_paths.py`, `src/bootstrap/deps_context.py`, `src/bootstrap/deps_runtime_verify.py`, `src/runtime/main_preflight.py`, `src/runtime/runtime_logging.py`, `src/runtime/single_instance.py`, `src/backend/model.py` | Runtime config, dependency state, dependency verification, crash logs, single-instance lock, dependency Python lookup, and LaTeX settings had multiple direct `Path.home() / ".latexsnipper"` paths. | macOS packaged apps should keep app-managed support files and logs under the user Library locations; scattered home-directory writes also made future sandbox review harder. | `runtime.app_paths` is now the shared source for app-managed state and logs. macOS state/config/deps use `~/Library/Application Support/LaTeXSnipper`; macOS logs use `~/Library/Logs/LaTeXSnipper`. Dependency bootstrap config, Pandoc layer verification, native crash logs, runtime logs, single-instance locking, model dependency lookup, and LaTeX settings now use the shared helpers. Verified with the project Python 3.11 compile and Ruff checks on touched modules. |
| fixed | macOS primary hotkey modifier | `src/runtime/hotkey_config.py`, `src/ui/hotkey_dialog.py`, `src/backend/qhotkey/qhotkey_macos.py`, `src/ui/main_window_setup.py`, `src/ui/hotkey_controller.py`, `src/ui/tray_controller.py`, `src/ui/predict_result_controller.py` | The user-facing global screenshot hotkey policy was `Ctrl+letter` on all platforms. | macOS users expect Command-based shortcuts; UI hints, stored defaults, tray text, and registration behavior could feel non-native. | Windows/Linux keep `Ctrl+F` and `Ctrl+Shift+letter`. macOS now defaults to `Command+F`, accepts `Command+letter` and `Command+Shift+letter` in the dialog, stores user-facing `Command` text, and maps it to Qt `Meta` before Carbon registration. Verified with compile, Ruff, and a hotkey normalization smoke test. |
| fixed | App temp grouping for preview assets | `src/runtime/app_paths.py`, `src/handwriting/document_preview_window.py`, `src/handwriting/pdf_view_poppler.py`, `src/backend/external_model/asset_store.py` | Fixed preview directories were scattered directly under the system temp root, and document preview reused its directory without clearing old build files at window startup. | Preview temp files could be harder to audit and stale files could remain visible to later preview sessions after a crash. | Added `app_temp_dir()` and moved document preview, Poppler SVG preview, and external PDF asset temp files under the shared app temp root. Document preview clears its build directory when the window is created; Poppler continues to clear between sessions. Verified with compile and Ruff checks. |
| fixed | History storage classification | `src/ui/main_window_setup.py`, `docs/user_data_storage.md` | `history_path` existed as an internal config key, but there is no UI for users to change the history file location. The storage map described it as user-changeable. | The data classification was misleading and the app carried a half-public path setting for history. | History is now treated as fixed app-managed state at `<app-state>/history.json`. Favorites remain user-relocatable through the favorites window. Verified with compile and Ruff checks. |
| fixed | MathCraft model cache root | `mathcraft_ocr/cache.py`, `src/ui/settings_environment_mixin.py` | MathCraft model weights previously used a package-owned hidden home directory on Linux/macOS, while the app state root had already moved to platform-native locations. | Model files were functional but not aligned with platform data conventions, especially on macOS. | Windows keeps `%APPDATA%\MathCraft\models`. Linux now defaults to `${XDG_DATA_HOME:-~/.local/share}/LaTeXSnipper/MathCraft/models`; macOS defaults to `~/Library/Application Support/LaTeXSnipper/MathCraft/models`. `MATHCRAFT_HOME` remains an explicit override. Settings opens the same directory resolved by `mathcraft_ocr.cache`. |
| fixed | Uninstall data cleanup | `Inno/latexsnipper.iss`, `scripts/latexsnipper-clean-user-data.sh`, `scripts/build_deb.sh`, `scripts/build_macos.sh`, `packaging/debian/DEBIAN/postrm` | Uninstall removed installed files but did not offer a clear path to delete app-managed state, dependency environments, temp files, logs, or MathCraft model weights. | Users who expected a clean uninstall could leave large model caches and dependency environments behind. | Windows uninstaller now prompts with separate app-data and model-weight cleanup checkboxes. Linux and macOS packages ship a current-user cleanup script because package uninstall must not implicitly delete arbitrary home-directory data. Custom `MATHCRAFT_HOME` directories are intentionally not deleted automatically. |
| fixed | Removed obsolete packaged-app channel | `src/runtime/distribution.py`, `src/update/update_dialog.py`, `src/ui/settings_layout_builder.py`, `LaTeXSnipper*.spec`, `scripts/`, `packaging/`, docs | The codebase still contained an unused alternate Windows packaging channel with separate update UI, manifest templates, channel metadata, and build scripts. | The open-source release flow does not need strong-sandbox packaging assumptions, and the extra channel logic increased maintenance surface. | Removed the alternate update dialog, build script, manifest template, spec branches, channel metadata generation, and user-facing documentation references. |

## Areas That Are Already Platform-Separated

- Platform providers are selected in `src/backend/platform/registry.py`.
- Screenshot capture has separate Windows, Linux, and macOS provider behavior,
  with Linux CLI/portal fallbacks and macOS Screen Recording preflight.
- Global hotkey backends are selected in `src/backend/qhotkey/__init__.py`.
- Release asset selection filters by platform in `src/update/release_assets.py`.
- Linux and macOS packages do not bundle the Windows `python311` template.
  They create user-writable dependency environments with supported system Python
  `>=3.10,<3.13`.
- Windows update auto-install is intentionally Windows-only; non-Windows update
  downloads currently stop at the downloaded package path.

## Cleanup Rules

- Do not move platform-specific process launching or package-manager logic into
  generic UI files. Prefer small helpers with explicit platform branches.
- Keep dependency bootstrap behavior aligned between Linux and macOS.
- Do not make the app run `sudo`, `apt`, `dnf`, `pacman`, `zypper`, or `brew`.
  Show instructions only.
- For every fixed item, record the target-platform validation that was run.
- Keep user-data storage documentation in `docs/user_data_storage.md` current
  when adding new persistent files, model caches, or reusable temp directories.

## Verification Baseline

The current audit baseline compiles successfully with:

```powershell
python -m compileall -q src mathcraft_ocr
```

Compilation only verifies syntax. It does not prove runtime behavior on Linux
or macOS.
