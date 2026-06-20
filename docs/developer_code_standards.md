# Developer Code Standards

These rules are mandatory for pull requests. They keep the desktop app,
MathCraft OCR package, dependency bootstrap flow, and platform packaging paths
clean and reproducible.

## Scope

- Keep platform code behind `backend/platform/*` providers and shared protocols.
- Keep screenshot fallback details in `cross_platform/screenshot_tools.py`.
- Do not put Linux/macOS branching, package-manager calls, or platform-specific
  setup UI directly in `main.py`, `ui/settings_window.py`, or the dependency wizard.
- Do not change installer files, dependency pins, startup behavior, or platform
  provider behavior outside the requested scope. Platform-specific changes need
  validation on that platform.

## Collaboration Workflow

- `main` is the release source of truth. Release packages should be built by
  GitHub Actions from `main` or from the final release tag, not from a local
  branch whose freshness is unknown.
- Feature work must be done on a branch and merged by pull request. Do not push
  direct feature commits to `main`.
- Before opening or updating a PR, sync the feature branch with the latest
  `main` and resolve conflicts locally:

```powershell
git fetch origin
git merge --ff-only origin/main
```

  If fast-forward is not possible, rebase or merge intentionally and document
  the conflict resolution in the PR.
- Repository branch protection or rulesets for `main` should require PR review,
  required status checks, and "require branches to be up to date before
  merging". This prevents merging a PR that has not been tested against the
  current `main`.
- After a PR is merged into `main`, any long-lived working branch such as
  `MathCraft` must be refreshed from `origin/main` before further development or
  packaging work:

```powershell
git fetch origin
git merge --ff-only origin/main
git push origin MathCraft
```

- If a local branch shows commits behind `origin/main`, do not create release
  artifacts from it. Update the branch first, then rely on the Actions release
  workflow for platform packages.
- If a PR changes packaging, dependency bootstrap, platform providers, or
  release workflows, the PR description must say which platform package jobs or
  local target-platform checks were run.
- Before platform cleanup work, check `docs/platform_adaptation_audit.md` and
  update the relevant status when the PR fixes or intentionally accepts an item.
- Before adding persistent user files, reusable caches, or temp directories,
  check and update `docs/user_data_storage.md`.

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
- Generated or downloaded dependency artifacts must not be stored in source
  package directories. In particular, keep local binaries out of `src/`, keep
  `*.egg-info/` out of commits, and use `tools/deps/`, build directories, or the
  app-managed user state directory for generated dependency state.
- Linux and macOS release specs must never collect `tools/deps/` or any
  build-machine virtual environment into the packaged app. Packaged Linux/macOS
  installs create dependency environments in the user's app state directory.
- Linux and macOS dependency bootstrap behavior must stay aligned. Both
  platforms use a supported system Python `>=3.10,<3.13` only to create the
  user-writable venv, preferring Python 3.11 when available. Runtime
  messages/docs must declare the platform-specific way to install that
  prerequisite. Do not accept newer Python versions until all dependency layers
  have been verified against them.
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
- Keep large UI windows and worker flows split by responsibility. New features
  should add focused controllers/helpers instead of growing already-large
  window modules.
- Keep comments short and technical. Avoid PR narrative, changelog prose, or
  long descriptive banners inside source files.
- Comments must explain durable implementation constraints, not historical
  decisions that no longer affect the code.

## Documentation Rules

- Keep Markdown documentation aligned with current code and packaging behavior.
  Do not keep retired setup paths, hidden feature flags, removed model IDs, or
  stale release artifact names.
- When user-facing behavior changes, update `readme.md`, `docs/faq.md`, and
  `user_manual/user_manual.md` when those documents mention the affected flow.
- Keep `user_manual/user_manual.md` and `user_manual/user_manual.typ` in sync
  when changing manual content, then rebuild the PDF when the user manual is the
  requested deliverable.
- Historical notes belong in release notes, not in current architecture,
  onboarding, or FAQ documents.

## Release Signing Rules

- Windows GitHub Release installers should be signed through SignPath when
  SignPath is configured and available.
- Release workflows must prefer the signed Windows installer artifact. If
  SignPath is unavailable or signing fails, the workflow may publish the
  unsigned Windows installer artifact so the final release still contains a
  Windows package.
- The Windows installer filename remains `LaTeXSnipperSetup-2.4.0.exe` for both
  signed and unsigned release assets.
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
