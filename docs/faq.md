# FAQ

## Where can I download LaTeXSnipper?

Download the latest installers from the [GitHub Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) page.

## Where is the full user manual?

The source manual is kept in `user_manual/` as Markdown and Typst. The generated PDF is rebuilt from `user_manual/user_manual.typ` and may be distributed as a release asset.

## Which platforms are supported?

LaTeXSnipper provides release builds for Windows, Linux, and macOS.

## What differs between Windows, Linux, and macOS?

The main application behavior is intentionally aligned across all three platforms: screenshot recognition, image recognition, PDF recognition, handwriting recognition, export, history, and favorites use the same UI flow.

The main differences are platform integration details:

| Area | Windows | Linux | macOS |
|---|---|---|---|
| Global screenshot hotkey | Native Win32 global hotkey. | `pynput` on X11; GlobalShortcuts portal on Wayland when supported by the desktop. | Native Carbon global hotkey. |
| User-configurable hotkeys | `Ctrl+letter` and `Ctrl+Shift+letter`. | `Ctrl+letter` and `Ctrl+Shift+letter`. | `Command+letter` / `Command+Shift+letter` for non-reserved keys; `Option+Command` variants are also supported. |
| Default hotkey | `Ctrl+F`. | `Ctrl+F`. | `Command+F`. |
| Screenshot capture | Qt overlay. | Qt overlay first, then optional CLI/portal fallbacks such as `grim`, `maim`, and `gnome-screenshot`. | Qt overlay with native `screencapture` fallback; macOS may ask for Screen Recording permission. |
| Window close / background behavior | Closing the main window hides it to the system tray; use the tray menu to exit. | Closing the main window hides it to the system tray when a tray is available; without a tray, the app asks before exiting. | Closing the main window hides it while the app keeps running; reopen it from the Dock or menu bar, and use Quit or Command+Q to exit. |
| Permission model | No explicit screenshot permission is required for the normal capture path. | Wayland global shortcuts require desktop authorization through the GlobalShortcuts portal; screenshot capture follows compositor policy. | Screen Recording permission is required for screenshots. The native Carbon hotkey path normally does not require Accessibility permission. |
| Inference runtime | Installed independent Python; CPU or NVIDIA GPU edition. | Installed independent Python; CPU or NVIDIA GPU edition. | Installed independent Python; Apple Silicon CPU edition. |
| Packaging | Inno installer with optional SignPath signing. | Offline `.tar.xz` carrier installing dpkg-owned components on Debian/Ubuntu. | `.dmg` / `.app` with ad-hoc signing. |

The shortcut UI uses the platform's primary modifier: `Ctrl` on Windows/Linux and `Command` on macOS. macOS system and editing shortcuts such as `Command+Q`, `Command+H`, `Command+M`, `Command+W`, `Command+A`, `Command+C`, `Command+V`, `Command+X`, `Command+Z`, `Command+Space`, `Command+Tab`, and screenshot shortcuts are intentionally rejected; use an `Option+Command` combination when a plain Command shortcut is reserved.

## Which installer should I use?

- Windows x86_64: choose the CPU or NVIDIA GPU `.exe` installer.
- Debian/Ubuntu-compatible Linux x86_64 with glibc 2.35 or newer: choose the CPU or NVIDIA GPU offline `.tar.xz`, extract it, and run `sh install.sh`.
- macOS 14.0 or later on Apple Silicon: use the CPU `.dmg`, copy the app to Applications, then launch that copy.

Windows installers are unsigned unless optional SignPath signing succeeds.
macOS builds use ad-hoc signatures without Developer ID or notarization. GPU builds
carry private CUDA/cuDNN user-mode libraries and require supported NVIDIA
hardware and drivers. The desktop app does not require system Python or CUDA
Toolkit. The 3.2.0 GPU editions require NVIDIA driver 570.65 or newer on Windows,
or 570.26 or newer on Linux. These minimums are declared in
`packaging/runtime/sources.lock.json`; the GPU must also support the bundled CUDA runtime.
Linux still requires its declared system GUI libraries. Its installer uses apt to
resolve missing system dependencies, which requires configured package sources
and network access unless the dependencies are already installed or cached.

## Why does macOS still say Screen Recording is unavailable after I enabled it?

LaTeXSnipper checks access with `CGPreflightScreenCaptureAccess()` before each
capture attempt. If access is missing, it requests it once with
`CGRequestScreenCaptureAccess()` and then opens the relevant System Settings
page. macOS associates this permission with the process that performs capture,
so the correct entry depends on how the application was started:

- For a packaged application opened from `/Applications/LaTeXSnipper.app`,
  authorize that exact `LaTeXSnipper` entry in **System Settings -> Privacy &
  Security -> Screen & System Audio Recording**. Older macOS versions call this
  pane **Screen Recording**.
- For a source checkout started with `python src/main.py`, authorize the entry
  that System Settings actually shows for the launch process, such as Python,
  Terminal, iTerm, or VS Code. It is not necessarily named LaTeXSnipper.
- Do not keep running the app directly from a mounted DMG, Downloads, or an
  App Translocation path. Move `LaTeXSnipper.app` to `/Applications`, quit with
  `Command+Q`, then relaunch that same copy before granting permission.

After changing the toggle, use `Command+Q` to quit the application completely;
closing the red window button alone does not exit the macOS app process. Open
the application again from the same location. If a development or test machine
has a stale TCC decision, reset it manually in Terminal and retry; the app never
runs these commands automatically:

```bash
tccutil reset ScreenCapture
# Packaged application only; the bundle identifier is stable.
tccutil reset ScreenCapture com.mathcraft.latexsnipper
```

If the permission preflight succeeds but capture still returns an empty image,
the failure is reported separately from OCR. Check the selected region,
multi-display layout, and `~/Library/Logs/LaTeXSnipper/` for Qt or
`screencapture` diagnostics.

## How do automation clients connect?

Automation API is disabled by default. After enabling it in Settings, local clients read `automation-api.json` from the application state directory and use its address and per-session Bearer token. Remote access must be explicitly enabled with a separate key and either HTTPS or an encrypted tunnel. See the [Automation API guide](automation_api.md).

## What is the Office plugin direction?

LaTeXSnipper Office integration is developed in the Windows-native `office_plugin` tree. The plugin provides persistent Ribbon loading, native KeyTip shortcuts, Word OLE and OMML formula insertion, PowerPoint OLE and PNG formula insertion, managed formula metadata, Word automatic numbering/references, and screenshot OCR as an authenticated Automation API client without requiring Microsoft 365 enterprise deployment.

## Why does Word OMML conversion report a missing Office stylesheet?

On Windows, desktop OMML export requires Microsoft Word registered in Windows
App Paths and `MML2OMML.XSL` beside `WINWORD.EXE`. The Word plugin loads
`MML2OMML.XSL` and `OMML2MML.XSL` from the running Word application's installation
directory when conversion is requested; missing stylesheets do not prevent the
plugin from starting. Custom installation directories are supported. If
registration or the required stylesheet is missing or damaged, repair the Office
installation and retry the operation.

## Does LaTeXSnipper require an internet connection?

Core editing and local recognition workflows are designed to work locally after a complete desktop installation. Business updates and source-mode model downloads require network access.

## Where are installation resources stored?

The installation separates business files in `application/` from the fixed Python, Qt/WebEngine, Pandoc, MathJax, inference dependencies and model weights. Business updates reuse the fixed base. A release requiring a different base directs you to its complete installer. Installation resources are separate from user data; see the [storage map](user_data_storage.md).

Source development uses the Python that starts the application and Pandoc from PATH. Packaged applications use their bundled runtimes. Linux tracks files through dpkg; macOS keeps the fixed base in an independently signed nested bundle.

## Where are logs stored?

- Windows: `%USERPROFILE%\.latexsnipper\logs\`
- Linux: `~/.latexsnipper/logs/`
- macOS: `~/Library/Logs/LaTeXSnipper/`

If the app crashes, include `crash-native.log` when reporting the issue.

## Where are MathCraft OCR models stored?

Packaged workers use only the installed model component. Missing or corrupt
weights are reported as resource failures; rerun the complete desktop installer
to restore the installed base. Source desktop workers use the platform default MathCraft
cache, which also serves the standalone library and CLI.
Platform locations are documented in the
[user data map](user_data_storage.md).

## What should I do if MathCraft OCR does not start?

Open **App diagnostics** and the runtime log. A packaged
resource failure requires rerunning the complete desktop installer. For source
development, check packages in the Python environment used to start the app.
GPU failures report hardware, driver or private-runtime problems. Changing the
installed CPU/GPU edition requires the matching installer; the app does not
silently select or install another backend.

## What if Linux fails with EGL, GLOzone, or GPU display errors?

This is usually a Qt WebEngine graphics-backend problem, not a MathCraft GPU inference problem. LaTeXSnipper automatically enables a software-rendering fallback for high-risk Linux sessions such as Wayland, virtual machines, WSL, or systems without `/dev/dri/renderD*`.

Manual overrides:

```bash
LATEXSNIPPER_FORCE_LINUX_GRAPHICS_FALLBACKS=1 latexsnipper
LATEXSNIPPER_DISABLE_LINUX_GRAPHICS_FALLBACKS=1 latexsnipper
```

## Why does Wayland ask me to authorize a global shortcut?

On Wayland, LaTeXSnipper registers its screenshot shortcut through the desktop's GlobalShortcuts portal. Complete the system authorization dialog; the desktop may assign a different combination, which LaTeXSnipper shows as the active shortcut. Cancelling a shortcut change keeps the previous authorized shortcut.

The desktop must provide `org.freedesktop.portal.GlobalShortcuts`. If registration fails, check that `xdg-desktop-portal` and the portal backend for your desktop are installed and running. Unsupported desktop environments can still use the screenshot button, or an X11 session for global shortcuts. Root privileges are not required.

## Why does screenshot capture behave differently on Wayland?

Wayland restricts application-level screen capture. LaTeXSnipper uses Qt capture first and can fall back to tools such as `grim`, `maim`, or `gnome-screenshot` when available. These system tools are installed by the user or distribution package manager, not by LaTeXSnipper.

## How is Pandoc provided?

Pandoc is only needed for the optional desktop export formats: Word `.docx`, ODT `.odt`, PowerPoint `.pptx`, EPUB `.epub`, PDF `.pdf`, standalone HTML `.html`, Typst `.typ`, and plain text `.txt`. PDF export also requires a LaTeX PDF engine such as XeLaTeX, LuaLaTeX, or pdfLaTeX. Core recognition, editing, preview, handwriting, and built-in LaTeX/Markdown/MathML/HTML/SVG exports work without Pandoc.

The fixed desktop runtime owns the Pandoc binary. Source development uses PATH Pandoc. The app does not install or uninstall it separately, persist its path, or modify PATH. If packaged Pandoc is missing, rerun the complete installer.

## How does PDF recognition work?

Use the main window's PDF recognition button and choose the page count, output format, and render DPI. Built-in MathCraft PDF recognition uses mixed mode because PDF pages need both text and formula recovery. External providers must be configured first. MinerU native mode sends the original PDF for document parsing, returns Markdown, and does not ask for render DPI.

The PDF result window lets you edit, copy, and save the recognized document. Markdown saves also copy structured image assets when the provider returns them.

## Which external model protocols are supported?

LaTeXSnipper supports the built-in MathCraft OCR path and external providers such as Ollama, OpenAI-compatible APIs, and MinerU Local. Recommended presets include GLM-OCR, PaddleOCR-VL, Qwen2.5/Qwen3-VL, and MinerU Local. For external providers, configure the protocol, Base URL, model name, API key when required, timeout, and prompt template.

The Base URL is the service root or the provider's `/v1` API prefix, not a concrete endpoint. The app appends protocol routes itself: Ollama uses `/api/tags` and `/api/chat`, OpenAI-compatible services use `/models` and `/chat/completions` under the resolved `/v1` prefix, and MinerU Local uses the configured health and parse paths.

The prompt template determines both the request instructions and result type for normal image and screenshot recognition. Handwriting uses a dedicated mixed-content template unless a custom prompt is supplied. A custom prompt replaces the built-in template for those paths and for OpenAI-compatible or Ollama PDF recognition. Built-in MathCraft and OpenAI-compatible or Ollama PDF recognition select output format and render DPI at the PDF entry point. MinerU Local parses the original PDF and does not use prompts or render DPI.

## Why does Ollama fail when I use `/v1`?

Ollama's native API does not use `/v1` for its model list. Use the Ollama protocol and test `http://127.0.0.1:11434/api/tags` first.

## How should I report a bug?

Open a GitHub Issue with:

- Operating system and package type
- Exact reproduction steps
- Full error text or screenshot
- The full `logs` directory
- `crash-native.log` if present
- External model configuration details if the issue involves an external provider

Issues without logs are usually not actionable.

## Which Python environment should contributors use?

Use a supported Python environment of your choice (venv, Conda, uv, or another manager). Activate it for development and checks, and select the same interpreter in your IDE. No repository-specific environment path is required. Desktop installers are built by `.github/workflows/release.yml`, which builds the business payload and assembles offline installers from persistent fixed-resource artifacts.

The release workflow's optional `validate_update` acceptance checks a published release.
With `publish_assets` disabled, it validates the existing release without rebuilding
or uploading assets.
It installs the published CPU package on Windows, Linux and macOS, creates an isolated
predecessor with the candidate's GUI code, then clicks the real update buttons to
verify application exit, business replacement and automatic restart. It also checks
installed identity, retained user data and the fixed inference runtime. The target
package and its independently authenticated release catalog remain unmodified.
Reports include exit and total update times; failure logs are retained as workflow
artifacts for seven days. This acceptance runs after publication and does not gate
release visibility. CUDA recognition acceptance remains a separate option.
