# FAQ

## Where can I download LaTeXSnipper?

Download the latest installers from the [GitHub Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) page.

## Where is the full user manual?

The full PDF user manual is distributed as a release asset when available. The source manual is kept in `user_manual/` in this repository, but that directory is not part of the normal source release workflow.

## Which platforms are supported?

LaTeXSnipper provides release builds for Windows, Linux, and macOS.

## Which installer should I use?

- Windows: use the signed Inno installer from GitHub Releases.
- Linux: use the `.deb` package on Debian/Ubuntu-compatible systems.
- macOS: use the `.dmg` or `.app.zip` artifact.

## Does LaTeXSnipper require an internet connection?

Core editing and local recognition workflows are designed to work locally after the required dependencies and models are installed. Some optional downloads, update checks, model downloads, and CDN fallbacks require network access.

## Where are dependency files stored?

- Windows packaged builds use the bundled dependency environment.
- Linux and macOS create runtime dependency files under `~/.latexsnipper/deps/python311`.

Linux/macOS release packages do not bundle the build-machine `src/deps/python311` environment.

## Why do Linux and macOS need Python 3?

The packaged app itself does not run on the user's system Python. Linux and macOS use system Python 3.10+ only to create the isolated optional dependency environment under `~/.latexsnipper/deps/python311`.

Linux `.deb` packages declare `python3` and `python3-venv`. macOS users should install Python with Homebrew (`brew install python`) or the official python.org macOS installer if no usable `python3` is available.

## Where are logs stored?

- Windows: `%USERPROFILE%\.latexsnipper\logs\` or `%LOCALAPPDATA%\LaTeXSnipper\logs\`
- Linux: `~/.latexsnipper/logs/`
- macOS: `~/.latexsnipper/logs/`

If the app crashes, include `crash-native.log` when reporting the issue.

## Where are MathCraft OCR models stored?

- Windows: `%APPDATA%\MathCraft\models\`
- Linux/macOS: `~/.mathcraft/models/`

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

Pandoc is only needed for optional export formats such as `.docx`, `.odt`, `.epub`, `.typ`, `.tex`, and wiki formats. Core recognition, editing, preview, handwriting, and built-in LaTeX/Markdown/MathML/HTML/SVG exports work without Pandoc.

## Which external model protocols are supported?

LaTeXSnipper supports the built-in MathCraft OCR path and external providers such as Ollama, OpenAI-compatible APIs, and MinerU-style services. For external providers, configure the protocol, base URL, model name, and API key when required.

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
