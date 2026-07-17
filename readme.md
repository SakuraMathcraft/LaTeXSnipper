# LaTeXSnipper ✨

<div align="center">

> A desktop math workspace for **capture -> recognize -> handwrite -> edit -> compute**
<img width="1919" height="1020" alt="封面" src="https://github.com/user-attachments/assets/9d00310b-d1b6-4321-b961-8837b3efb864" />

![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Stars&color=FFD700)
![Forks](https://img.shields.io/github/forks/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Forks&color=1f6feb)
![Issues](https://img.shields.io/github/issues/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Issues&color=d1481e)
![License](https://img.shields.io/badge/license-GPLv3-blue?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-orange?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11-blue?style=flat-square)

[![GitHub Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square&include_prereleases)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
[![Last Commit](https://img.shields.io/github/last-commit/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Activity)](https://github.com/SakuraMathcraft/LaTeXSnipper/graphs/commit-activity)

[FAQ](docs/faq.md) · [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) · [LINUX DO Community](https://linux.do/)

English · [简体中文](README.zh-CN.md)

</div>

---

## Core Features

| Feature | Description |
|------|------|
| 📸 Formula recognition | MathCraft OCR for formulas, text, and mixed content |
| 📄 PDF recognition | Page-based PDF recognition with Markdown/LaTeX output and DPI control |
| ✍️ Handwriting recognition | Dedicated handwriting window with auto-recognition and live preview |
| 🧮 Math workbench | Separate workspace for editing, computation, and write-back |
| ⌨️ Formula editing | Integrated `MathLive math-field` with virtual math keyboard |
| 🔄 Multi-format export | 20 export formats across LaTeX, Markdown, MathML, HTML, OMML, SVG, Word, ODT, PowerPoint, EPUB, PDF, Typst, and plain text |
| 📐 Core computation | Compute, simplify, numeric evaluate, expand, factor, solve |
| 🌙 Theme support | Light/Dark adaptation across windows and tools |
| 🔐 Offline-first | Recognition and computation can run locally for privacy |

MathCraft OCR benchmark results: [tables and charts](https://github.com/SakuraMathcraft/MathCraft-Models/tree/main/benchmarks) · [reproduction suite](benchmarks/mathcraft_ocr/README.md)

---

## Microsoft Office Plugin

LaTeXSnipper provides a released Windows plugin for desktop Microsoft Word and PowerPoint:

- Word OLE and native OMML formula insertion
- PowerPoint OLE and PNG formula insertion
- Shared MathLive editor and extensive symbol/formula library
- Formula loading, update, deletion, automatic numbering, and renumbering
- Persisted complete LaTeX source, rendering options, numbering data, and formula identity
- Local vector rendering for OLE formulas
- Screenshot recognition through the local desktop Bridge

Download `OfficePluginSetup-<version>.exe` from [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases). The plugin supports 32-bit and 64-bit desktop Office 2019, 2021, 2024, LTSC 2021/2024, and Microsoft 365 Apps on Windows.

See the [Office plugin documentation](office_plugin/README.md) for requirements and release build details.

---

## Export Formats

LaTeXSnipper exposes a shared export menu in the main window and favorites window. The desktop app currently provides 20 export formats.

Built-in formula export formats:

- LaTeX inline, display, and equation
- Markdown inline and block math
- MathML standard, `.mml`, `<m>`, and attribute forms
- HTML, Word OMML, and SVG code

Optional Pandoc export formats are enabled after installing the `PANDOC` layer in the dependency wizard:

- Word `.docx`, ODT `.odt`, PowerPoint `.pptx`, EPUB `.epub`
- PDF `.pdf` (requires Pandoc plus a LaTeX PDF engine such as XeLaTeX, LuaLaTeX, or pdfLaTeX)
- Standalone HTML `.html`, Typst `.typ`, and plain text `.txt`

---

## Platform Support

| Platform | Status | Notes |
|------|------|------|
| Windows | Primary release target | Native global hotkey, Qt capture, GitHub/Inno packaging. |
| Linux | Supported via provider layer | `pynput` global hotkey, Qt capture first, optional Wayland/X11 CLI or portal fallbacks. |
| macOS | Supported via provider layer | Native global hotkey, Qt capture with `screencapture` fallback, Screen Recording permission may be required. |

Linux and macOS both create optional runtime dependency environments in the
user state directory, so they need a usable system Python `>=3.10,<3.13` with
venv/pip support. Python 3.11 is preferred because it matches the Windows
bundled runtime. Debian/Ubuntu `.deb` installs declare `python3` and
`python3-venv`; macOS users should install Homebrew `python@3.11` or an
official python.org 3.11/3.12 installer when the system does not provide a
usable supported `python3`.

---

## Supporters

Thanks to everyone who supports LaTeXSnipper development, testing, documentation, and community maintenance.

| Supporter | Contribution |
|---|---|
| [strangelion](https://github.com/strangelion) | contributor |
| [Galileo927](https://github.com/Galileo927) | contributor |
| [ljygo](https://github.com/ljygo) | Sponsor |
| [Yokie-D](https://github.com/Yokie-D) | Sponsor |

---

## Support The Project

LaTeXSnipper is a free, open-source, ad-free personal project. If it helps with your writing, OCR, or formula workflow, small sponsorships and community feedback help keep maintenance moving.

| 支付宝 | 微信 | 交流群 |
|--------|------|--------|
| <img width="300" alt="支付宝收款码" src="https://github.com/user-attachments/assets/1efa46b7-07cb-4a3e-821d-f23b7a36ab34" /> | <img width="300" alt="微信收款码" src="https://github.com/user-attachments/assets/19065b1d-ac40-478e-8318-fabb75488c5c" /> | <img width="300" alt="LaTeXSnipper群聊" src="https://github.com/user-attachments/assets/91c30d59-a4a7-4118-b24b-dada0fe002bf" /> |

---

## License

This project is open-sourced under the [GNU General Public License v3](LICENSE).
