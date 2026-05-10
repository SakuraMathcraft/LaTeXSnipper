# Developer Code Standards

These rules are mandatory for pull requests. They protect the Windows release
path while allowing Linux and macOS support to evolve cleanly.

## Scope

- Keep platform code behind `backend/platform/*` providers and shared protocols.
- Keep screenshot fallback details in `cross_platform/screenshot_tools.py`.
- Do not put Linux/macOS branching, package-manager calls, or platform-specific
  setup UI directly in `main.py`, `settings_window.py`, or the dependency wizard.
- Do not change Windows installer files, Windows dependency pins, or Windows
  startup behavior as part of a Linux/macOS PR unless the PR explicitly targets
  Windows and includes separate Windows validation.

## Dependency Rules

- The dependency wizard must only manage the app's Python dependency layers.
- It must not run or suggest automated `sudo`, `apt`, `dnf`, `pacman`, `zypper`,
  `brew`, or system package install/uninstall commands.
- System tools such as `grim`, `maim`, `gnome-screenshot`, and `screencapture`
  are optional runtime fallbacks. They may be detected and documented, but not
  installed by the app.
- The root `python311` directory is a template runtime. Build scripts must not
  write dependencies into it. Build/runtime dependencies belong under
  `src/deps/python311`.
- Keep common `requirements.txt` minimal. Put Linux/macOS additions in
  `requirements-linux.txt` and `requirements-macos.txt`.
- Keep the Pandoc build wrapper pinned in `requirements-build.txt` unless the
  PR explicitly updates and verifies the Pandoc packaging flow.

## Packaging Rules

- Linux/macOS packaging files may be added only when they are complete enough to
  be run by a maintainer on the target platform.
- Scripts must be deterministic, path-scoped to the repository, and must not
  mutate template runtimes or user-level environments.
- Prefer portable shell/Python logic over platform-specific GNU extensions when
  the script targets macOS.
- README references to packaging scripts or spec files must point to files that
  exist in the repository.

## Clean Code Rules

- No dead functions, dead flags, placeholder layers, duplicate UI controls, or
  unused package maps.
- No settings UI for behavior already owned by the dependency wizard or provider
  layer.
- No broad refactors mixed into platform support PRs.
- Keep comments short and technical. Avoid PR narrative, changelog prose, or
  long descriptive banners inside source files.

## Required Validation

Run all checks with the project dependency Python:

```powershell
.\src\deps\python311\python.exe -m ruff check .
.\src\deps\python311\python.exe -m pytest test
.\src\deps\python311\python.exe -m pyright
.\src\deps\python311\python.exe -m compileall -q -x "src[\\/]+deps" src mathcraft_ocr test
```

For packaging changes, also validate the relevant script/spec on the target
platform and include the command and result in the PR description.
