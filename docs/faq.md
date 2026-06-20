# FAQ

## Where can I download LaTeXSnipper?

Download the latest installers from the [GitHub Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) page.

## Where is the full user manual?

The source manual is kept in `user_manual/` as Markdown and Typst. The generated PDF is rebuilt from `user_manual/user_manual.typ` and may be distributed as a release asset.

## Which platforms are supported?

LaTeXSnipper provides release builds for Windows, Linux, and macOS.

## What differs between Windows, Linux, and macOS?

The main application behavior is intentionally aligned across all three platforms: screenshot recognition, image recognition, PDF recognition, handwriting recognition, bilingual reading, export, history, favorites, and the math workbench use the same UI flow.

The main differences are platform integration details:

| Area | Windows | Linux | macOS |
|---|---|---|---|
| Global screenshot hotkey | Native Win32 global hotkey. | `pynput` global hotkey; X11 is the most reliable path, while Wayland/compositor policy can block global shortcuts. | Native Carbon global hotkey. |
| User-configurable hotkeys | `Ctrl+letter` and `Ctrl+Shift+letter`. | `Ctrl+letter` and `Ctrl+Shift+letter`. | `Command+letter` and `Command+Shift+letter`. |
| Default hotkey | `Ctrl+F`. | `Ctrl+F`. | `Command+F`. |
| Screenshot capture | Qt overlay. | Qt overlay first, then optional CLI/portal fallbacks such as `grim`, `maim`, and `gnome-screenshot`. | Qt overlay with native `screencapture` fallback; macOS may ask for Screen Recording permission. |
| Window close / background behavior | Closing the main window hides it to the system tray; use the tray menu to exit. | Closing the main window hides it to the system tray when a tray is available; without a tray, the app asks before exiting. | Closing the main window minimizes it while the app keeps running; Dock/menu Quit exits the app. |
| Permission model | No explicit screenshot permission is required for the normal capture path. | Wayland compositors can restrict global shortcuts or screenshot capture. | Screen Recording permission is required for screenshots. The native Carbon hotkey path normally does not require Accessibility permission. |
| Dependency runtime | GitHub builds bundle the normalized dependency runtime. | Creates `~/.latexsnipper/deps/python311` with system Python `>=3.10,<3.13` and venv/pip support. | Creates `~/Library/Application Support/LaTeXSnipper/deps/python311` with system Python `>=3.10,<3.13` and venv/pip support. |
| Packaging | Inno installer from GitHub Releases. | Debian/Ubuntu `.deb`. | `.dmg` and `.app.zip`. |

The shortcut UI uses the platform's primary modifier: `Ctrl` on Windows/Linux and `Command` on macOS.

## Which installer should I use?

- Windows: use `LaTeXSnipperSetup-<version>.exe` from GitHub Releases. The release workflow prefers the signed installer; if signing is unavailable, the same filename may be published as an unsigned fallback.
- Linux: use the `.deb` package on Debian/Ubuntu-compatible systems.
- macOS: use the `.dmg` or `.app.zip` artifact.

## What is the Office plugin direction?

LaTeXSnipper Office integration is developed in the Windows-native `office_plugin` tree. The plugin provides persistent Ribbon loading, native KeyTip shortcuts, Word OMML insertion, managed formula metadata, screenshot OCR integration, and a local Bridge pipeline without requiring Microsoft 365 enterprise deployment.

## Does LaTeXSnipper require an internet connection?

Core editing and local recognition workflows are designed to work locally after the required dependencies and models are installed. Some optional downloads, update checks, model downloads, and CDN fallbacks require network access.

## Where are dependency files stored?

- Windows builds use the bundled dependency environment.
- Linux creates runtime dependency files under `~/.latexsnipper/deps/python311`.
- macOS creates runtime dependency files under `~/Library/Application Support/LaTeXSnipper/deps/python311`.

Linux/macOS release packages do not bundle build-machine environments from `tools/deps/`.

## When does the dependency wizard initialize pip?

The dependency wizard opens before running `ensurepip`, `pip` upgrade, or `setuptools`/`wheel` repair. Those steps run only after the user starts dependency installation.

If the selected directory already contains a usable Python environment, the wizard uses that interpreter and installs the selected layers there. If no usable Python environment exists, Windows initializes the local `python311` template through the bundled `python-3.11.0-amd64.exe`, while Linux/macOS use system Python `>=3.10,<3.13` to create the isolated environment.

## Why do Linux and macOS need Python 3?

The packaged app itself does not run on the user's system Python. Linux and macOS use system Python `>=3.10,<3.13` only to create the isolated optional dependency environment. Linux uses `~/.latexsnipper/deps/python311`; macOS uses `~/Library/Application Support/LaTeXSnipper/deps/python311`. Python 3.11 is preferred because it matches the Windows bundled runtime; Python 3.13+ is intentionally rejected until all dependency layers are verified against it.

Linux `.deb` packages declare `python3` and `python3-venv`. macOS users should install a supported Python, preferably Homebrew `python@3.11` or the official python.org 3.11/3.12 macOS installer, if no usable `python3` is available.

## Where are logs stored?

- Windows: `%USERPROFILE%\.latexsnipper\logs\` or `%LOCALAPPDATA%\LaTeXSnipper\logs\`
- Linux: `~/.latexsnipper/logs/`
- macOS: `~/Library/Logs/LaTeXSnipper/`

If the app crashes, include `crash-native.log` when reporting the issue.

## Where are MathCraft OCR models stored?

- Windows: `%APPDATA%\MathCraft\models\`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/LaTeXSnipper/MathCraft/models/`
- macOS: `~/Library/Application Support/LaTeXSnipper/MathCraft/models/`

If a model download is interrupted or corrupted, delete the affected model subdirectory and restart LaTeXSnipper.

## What should I do if MathCraft OCR does not start?

Run the dependency wizard first. If the issue persists, check the logs and verify the model cache with:

```bash
python -m mathcraft_ocr models check
```

For GPU-related ONNX Runtime failures, use CPU mode:

```bash
MATHCRAFT_FORCE_ORT_CPU=1
```

## Does Linux/macOS bundle Python like Windows?

No. Windows has a normalized bundled Python template. Linux/macOS packages contain the PyInstaller app and create a user-writable dependency environment on demand. This avoids permission errors and prevents build-host virtual environments from leaking into release packages.

## What if Linux fails with EGL, GLOzone, or GPU display errors?

This is usually a Qt WebEngine graphics-backend problem, not a MathCraft GPU inference problem. LaTeXSnipper automatically enables a software-rendering fallback for high-risk Linux sessions such as Wayland, virtual machines, WSL, or systems without `/dev/dri/renderD*`.

Manual overrides:

```bash
LATEXSNIPPER_FORCE_LINUX_GRAPHICS_FALLBACKS=1 latexsnipper
LATEXSNIPPER_DISABLE_LINUX_GRAPHICS_FALLBACKS=1 latexsnipper
```

## Why does screenshot capture behave differently on Wayland?

Wayland restricts application-level screen capture. LaTeXSnipper uses Qt capture first and can fall back to tools such as `grim`, `maim`, or `gnome-screenshot` when available. These system tools are installed by the user or distribution package manager, not by LaTeXSnipper.

## Why is Pandoc optional?

Pandoc is only needed for the optional desktop export formats: Word `.docx`, ODT `.odt`, PowerPoint `.pptx`, EPUB `.epub`, PDF `.pdf`, standalone HTML `.html`, Typst `.typ`, and plain text `.txt`. PDF export also requires a LaTeX PDF engine such as XeLaTeX, LuaLaTeX, or pdfLaTeX. Core recognition, editing, preview, handwriting, and built-in LaTeX/Markdown/MathML/HTML/SVG exports work without Pandoc.

The dependency wizard manages the optional `PANDOC` layer. Manually downloaded or generated Pandoc binaries should not live under `src/`; local developer/build tools belong under `tools/deps/` or the app-managed dependency directory.

## How does PDF recognition work?

Use the main window's PDF recognition button and choose the page count, output format, and render DPI. Built-in MathCraft PDF recognition uses mixed mode because PDF pages need both text and formula recovery. External providers must be configured first; MinerU native mode uses document parsing and returns Markdown.

The PDF result window lets you edit, copy, and save the recognized document. Markdown saves also copy structured image assets when the provider returns them.

## What is Bilingual Reading?

Bilingual Reading is a PDF reading and translation window, not OCR. It reads the PDF text layer with PyMuPDF, shows the current page beside the extracted source text, and translates with one of these engines:

- source text only
- Argos Translate
- Azure Translator
- Google Cloud Translation
- DeepL API Free

Scanned PDFs without a text layer should be processed through PDF recognition first. Argos uses an optional independent translation environment. Remote engines require their own API keys and their configuration only applies to Bilingual Reading.

## Which external model protocols are supported?

LaTeXSnipper supports the built-in MathCraft OCR path and external providers such as Ollama, OpenAI-compatible APIs, and MinerU-style services. Recommended presets include GLM-OCR, PaddleOCR-VL, Qwen2.5/Qwen3-VL, Ollama Vision, and MinerU Native. For external providers, configure the protocol, base URL, model name, API key when required, output preference, timeout, and prompt template.

External output preference affects normal image, screenshot, and handwriting recognition. PDF recognition asks for output format and DPI at the PDF entry point.

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

Use `tools/deps/python311` for local development, checks, packaging helpers, and IDE integration. The repository-root `python311/` is the Windows template runtime and must not be polluted with development packages or used for ruff, pyright, pytest, or builds.
