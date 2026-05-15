                         # Developer Code Standards

These rules are mandatory for pull requests. They protect the Windows release
path while allowing Linux and macOS support to evolve cleanly.

## Scope

- Keep platform code behind `backend/platform/*` providers and shared protocols.
- Keep screenshot fallback details in `cross_platform/screenshot_tools.py`.
- Do not put Linux/macOS branching, package-manager calls, or platform-specific
  setup UI directly in `main.py`, `ui/settings_window.py`, or the dependency wizard.
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
- The root `python311` directory is the Windows template runtime. Build scripts
  must not install application dependencies into it or mutate it as a developer
  environment.
- Any bundled Python runtime must come from a clean, self-contained,
  self-referential template. It must not contain `pyvenv.cfg`, build-host
  prefixes, or paths outside the bundled runtime, and the build must verify
  `sys.prefix`, `sys.base_prefix`, and `sys.path` before packaging.
- Empty or first-run dependency configuration must still resolve the intended
  internal Python environment automatically when that platform intentionally
  bundles one.
- Project dependency/build environments belong under `tools/deps/`, never under
  `src/`. The Windows developer interpreter is `tools/deps/python311`; Linux and
  macOS build scripts create platform-scoped venvs such as
  `tools/deps/python311-linux-x86_64`. These environments may be used to run
  PyInstaller and collect required runtime files, but must never be copied as an
  embedded Python runtime.
- Linux and macOS release specs must never collect `tools/deps/` or any
  build-machine virtual environment into the packaged app. Packaged Linux/macOS
  installs create dependency environments in the user's app state directory.
- Linux and macOS dependency bootstrap behavior must stay aligned. Both
  platforms use a system Python 3.10+ only to create the user-writable venv, and
  runtime messages/docs must declare the platform-specific way to install that
  prerequisite.
- Keep common app runtime packages in `requirements.txt`. Platform files may
  include it and then add Linux/macOS-only packages.
- Keep build tools pinned in `requirements-build.txt` unless the PR explicitly
  updates and verifies the packaging flow.

## Packaging Rules

- Linux/macOS packaging files may be added only when they are complete enough to
  be run by a maintainer on the target platform.
- Scripts must be deterministic, path-scoped to the repository, and must not
  mutate template runtimes or user-level environments.
- Prefer portable shell/Python logic over platform-specific GNU extensions when
  the script targets macOS.
- README references to packaging scripts or spec files must point to files that
  exist in the repository.
- GitHub Actions release builds must keep Windows, Linux, macOS, and release
  publishing jobs in one workflow unless the PR explicitly changes release
  policy and documents the replacement.

## Language And Encoding Rules

- All source-code comments and docstrings must be written in English. User-facing
  application strings may remain localized, but explanatory code text must not.
- Packaging and automation files must be English-only and ASCII-only. This
  includes `.github/workflows/*`, `scripts/*.sh`, `*.spec`, `requirements*.txt`,
  and `packaging/debian/DEBIAN/*`.
- Shell scripts, workflow files, PyInstaller spec files, and Debian maintainer
  scripts must use LF line endings. Do not add localized comments, banners, or
  terminal output to these files.
- User-facing application strings and README content may be localized when the
  localization is intentional and encoded as UTF-8.
- Do not add mixed-encoding text, garbled comments, or copied terminal prose to
  source files. If a comment is needed, keep it short, technical, and readable.
- Python source must be UTF-8 without BOM. Do not rewrite files with UTF-8 BOM,
  locale-specific encodings, or mixed line endings.

## Clean Code Rules

- No dead functions, dead flags, placeholder layers, duplicate UI controls, or
  unused package maps.
- No settings UI for behavior already owned by the dependency wizard or provider
  layer.
- No broad refactors mixed into platform support PRs.
- Keep comments short and technical. Avoid PR narrative, changelog prose, or
  long descriptive banners inside source files.
- Comments must explain durable implementation constraints, not historical
  decisions that no longer affect the code.

## Release Signing Rules

- Windows GitHub Release installers must be signed through SignPath before they
  are uploaded to a GitHub Release.
- Release workflows must publish the signed installer artifact only. Unsigned
  Windows installer artifacts are build intermediates for SignPath and must not
  be matched by release upload globs.
- Keep the SignPath artifact configuration in
  `.signpath/artifact-configurations/windows-installer.xml` synchronized with
  the SignPath project configuration. The GitHub artifact uploaded for signing
  is a zip file whose root contains `LaTeXSnipperSetup-*.exe`.
- Store `SIGNPATH_ORGANIZATION_ID`, `SIGNPATH_PROJECT_SLUG`,
  `SIGNPATH_SIGNING_POLICY_SLUG`, and
  `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` as GitHub Actions variables.
- Store `SIGNPATH_API_TOKEN` as a GitHub Actions secret. SignPath identifiers,
  tokens, certificate material, and private organization values must never be
  committed to source files.
- Follow the SignPath GitHub trusted build system documentation and artifact
  configuration schema:
  `https://docs.signpath.io/trusted-build-systems/github` and
  `https://about.signpath.io/documentation/artifact-configuration`.

## Required Validation

Run all checks with the project dependency Python:

```powershell
.\tools\deps\python311\python.exe -m ruff check .
.\tools\deps\python311\python.exe -m pytest test
.\tools\deps\python311\python.exe -m pyright
.\tools\deps\python311\python.exe -m compileall -q src mathcraft_ocr test
```

For packaging changes, also validate the relevant script/spec on the target
platform and include the command and result in the PR description.
