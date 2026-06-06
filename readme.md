# LaTeXSnipper ✨

<div align="center">

> A desktop math workspace for **capture -> recognize -> handwrite -> edit -> compute**
<img width="1919" height="1020" alt="封面" src="https://github.com/user-attachments/assets/9d00310b-d1b6-4321-b961-8837b3efb864" />

![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Stars&color=FFD700)
![Forks](https://img.shields.io/github/forks/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Forks&color=1f6feb)
![Issues](https://img.shields.io/github/issues/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Issues&color=d1481e)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)
![Version](https://img.shields.io/badge/version-v2.3.2_Final_Stable-brightgreen?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-orange?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11-blue?style=flat-square)

[![GitHub Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square&include_prereleases)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
[![Last Commit](https://img.shields.io/github/last-commit/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Activity)](https://github.com/SakuraMathcraft/LaTeXSnipper/graphs/commit-activity)

### Star History

[![Star History Chart](https://api.star-history.com/svg?repos=SakuraMathcraft/LaTeXSnipper&type=Date)](https://star-history.com/#SakuraMathcraft/LaTeXSnipper&Date)

[FAQ](docs/faq.md) · [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)

</div>

---

## Core Features

| Feature | Description |
|------|------|
| 📸 Formula recognition | MathCraft OCR for formulas, text, and mixed content |
| 📄 PDF recognition | Page-based PDF recognition with Markdown/LaTeX output and DPI control |
| 🌐 Bilingual reading | PDF text-layer reading with local Argos or remote translation engines |
| ✍️ Handwriting recognition | Dedicated handwriting window with auto-recognition and live preview |
| 🧮 Math workbench | Separate workspace for editing, computation, and write-back |
| ⌨️ Formula editing | Integrated `MathLive math-field` with virtual math keyboard |
| 🔄 Multi-format export | 30 export choices across LaTeX, Markdown, MathML, HTML, OMML, SVG, Typst, Word, EPUB, RTF, wiki formats, and more |
| 📐 Core computation | Compute, simplify, numeric evaluate, expand, factor, solve |
| 🧠 Advanced fallback | Local `SymPy/mpmath` engine for harder expressions |
| 🌙 Theme support | Light/Dark adaptation across windows and tools |
| 🔐 Offline-first | Recognition and advanced solving can run locally for privacy |

---

## Microsoft Office Plugin

LaTeXSnipper provides a released Windows plugin for desktop Microsoft Word and PowerPoint:

- Word OLE and native OMML formula insertion
- PowerPoint OLE and PNG formula insertion
- Shared MathLive editor and extensive symbol/formula library
- Formula loading, update, deletion, automatic numbering, and renumbering
- Persisted LaTeX source, rendering options, numbering data, and formula identity
- Local vector rendering for OLE formulas
- Screenshot recognition through the local desktop Bridge

Download `OfficePluginSetup-<version>.exe` from [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases). The plugin supports 32-bit and 64-bit desktop Office 2019, 2021, 2024, LTSC 2021/2024, and Microsoft 365 Apps on Windows.

See the [Office plugin documentation](office_plugin/README.md) for requirements and release build details.

---

## Computation Coverage

The workbench currently covers common scenarios such as:

- Polynomial expansion
- Factorization
- Equation solving
- Irrational/complex root fallback solving
- Definite and improper integrals
- Infinite series
- Infinite products
- Limits
- Derivatives
- Numeric approximation and constant recognition

---

## Export Formats

LaTeXSnipper exposes a shared export menu in the main window and favorites window.

Built-in formula export formats:

- LaTeX inline, display, and equation
- Markdown inline and block math
- MathML standard, `.mml`, `<m>`, and attribute forms
- HTML, Word OMML, and SVG code

Optional Pandoc export formats are enabled after installing the `PANDOC` layer in the dependency wizard:

- Word `.docx`, ODT `.odt`, EPUB `.epub`, InDesign `.icml`
- RTF, plain text, standalone HTML, LaTeX `.tex`, Typst `.typ`
- GitHub Markdown, CommonMark, reStructuredText
- MediaWiki, DokuWiki, Org-mode, Textile, Jira Wiki, and man page output

---

## Quick Start

### Option 1: Download the executable

1. Visit the [Releases page](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
2. Download the latest `LaTeXSnipperSetup-<version>.exe`
3. Run the installer
4. Complete environment setup via the dependency wizard on first launch
5. Start capturing, handwriting, or using the math workbench

### Option 2: Run from source

Windows:

```bash
git clone https://github.com/SakuraMathcraft/LaTeXSnipper.git
cd LaTeXSnipper

python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt
python src/main.py
```

Linux:

```bash
git clone https://github.com/SakuraMathcraft/LaTeXSnipper.git
cd LaTeXSnipper

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements-linux.txt
python src/main.py
```

macOS:

```bash
git clone https://github.com/SakuraMathcraft/LaTeXSnipper.git
cd LaTeXSnipper

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements-macos.txt
python src/main.py
```

---

## Platform Support

| Platform | Status | Notes |
|------|------|------|
| Windows | Primary release target | Native global hotkey, Qt capture, GitHub/Inno and Store/MSIX packaging. |
| Linux | Supported via provider layer | `pynput` global hotkey, Qt capture first, optional Wayland/X11 CLI or portal fallbacks. |
| macOS | Supported via provider layer | Native global hotkey, Qt capture with `screencapture` fallback, Screen Recording permission may be required. |

Linux and macOS both create optional runtime dependency environments in the
user state directory, so they need a usable system Python 3.10+ with venv/pip
support. Debian/Ubuntu `.deb` installs declare `python3` and `python3-venv`;
macOS users should install Python through Homebrew (`brew install python`) or
the official python.org macOS installer when the system does not provide a
usable `python3`.

---

## Contributing

Contributions are welcome:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push your branch
5. Open a Pull Request

All pull requests must follow [Developer Code Standards](docs/developer_code_standards.md).
Before requesting review, run:

```powershell
.\tools\deps\python311\python.exe -m ruff check .
.\tools\deps\python311\python.exe -m pytest test
.\tools\deps\python311\python.exe -m pyright
.\tools\deps\python311\python.exe -m compileall -q src mathcraft_ocr test
```

---

## License

This project is open-sourced under the [MIT License](LICENSE).
