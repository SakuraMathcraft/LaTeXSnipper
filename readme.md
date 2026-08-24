# LaTeXSnipper ✨

<div align="center">

> A cross-platform math OCR workspace and automation service for **capture -> recognize -> handwrite -> edit -> integrate**
<img width="1919" height="1021" alt="LaTeXSnipper v3.0.0" src="docs/latexsnipper-3.0.0.png" />

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
| 📸 Formula recognition | MathCraft OCR or a configured local/online external model for formulas, text, and mixed content |
| 📄 PDF recognition | Page-based PDF recognition with Markdown/LaTeX output and DPI control |
| ✍️ Handwriting recognition | Dedicated handwriting window with auto-recognition and live preview |
| 🔌 Automation API | Local scripts, batch jobs, editor tools, and securely authorized remote devices |
| 🧩 Application integration | Official Word/PowerPoint client plus AutoKey, AutoHotkey, Hammerspoon, ShareX, and mobile workflows |
| ⌨️ Formula editing | Integrated `MathLive math-field` with virtual math keyboard |
| 🔄 Multi-format export | 20 export formats across LaTeX, Markdown, MathML, HTML, OMML, SVG, Word, ODT, PowerPoint, EPUB, PDF, Typst, and plain text |
| 🧮 Math workbench | Separate workspace for editing, computation, and write-back |
| 📐 Core computation | Compute, simplify, numeric evaluate, expand, factor, solve |
| 🌙 Theme support | Light/Dark adaptation across windows and tools |
| 🔐 Offline-first | Recognition and computation can run locally for privacy |

MathCraft OCR benchmark results: [tables and charts](https://github.com/SakuraMathcraft/MathCraft-Models/tree/main/benchmarks) · [reproduction suite](benchmarks/mathcraft_ocr/README.md)

---

## Automation API

Automation API exposes both the resident MathCraft model and the desktop application's configured external model through controlled `mathcraft` and `external` backends. MathCraft and external calls use separate bounded, single-concurrency executors, so slow Ollama, MinerU, or online requests do not block MathCraft. Clients cannot read or override upstream URLs, model names, credentials, or prompts.

It accepts eight common image extensions—PNG, JPG, JPEG, BMP, GIF, TIF, TIFF, and WEBP—covering six actual encodings. The most useful real-world combinations are:

- **Snipaste + AutoHotkey/AutoKey/Hammerspoon:** recognize a screenshot and write the result back to the clipboard.
- **ShareX + Automation API:** upload and recognize automatically after a capture finishes.
- **VS Code/TeXstudio/Obsidian plugins:** insert recognition output directly at the editing position.
- **iOS Shortcuts/Android Tasker + Tailscale:** call the resident MathCraft runtime on a home computer from a phone.
- **Python/curl + batch API:** batch-recognize an entire image directory with a custom workflow.

The API is **disabled by default** and defaults to local-only `127.0.0.1:28765`. Local clients discover the actual address and per-session Bearer token in the private `automation-api.json` connection file. AutoKey, AutoHotkey, Hammerspoon, ShareX, editor plugins, and the official Office plugin can use this local flow. Upload decoding is serialized and normalized images remain inside a shared memory budget until recognition finishes, preventing concurrent large uploads from multiplying memory use.

Remote access requires explicit user opt-in, a separate remote key, and either an encrypted Tailscale/WireGuard/SSH-style tunnel or HTTPS. Plain public-internet HTTP is not supported. Remote external-model access is disabled by default because it can consume third-party quota or local resources. Automation clients never open desktop capture UI; they submit existing images. The official Office client can locally wait for a copy of the next user-initiated desktop recognition result.

Minimal local call after reading `base_url` and `token` from the connection file:

```bash
curl "$BASE_URL/api/v1/recognition/jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Prefer: wait=30" \
  -F backend=mathcraft \
  -F mode=formula \
  -F "images=@formula.png"
```

Secure remote calls use the same route with an HTTPS or encrypted-tunnel `BASE_URL` and the independently generated remote key. See the [complete API reference](docs/automation_api.md) and [client examples](examples/automation/).

---

## Microsoft Office Plugin

LaTeXSnipper provides a released Windows plugin for desktop Microsoft Word and PowerPoint:

- Word OLE and native OMML formula insertion
- PowerPoint OLE and PNG formula insertion
- Shared MathLive editor and extensive symbol/formula library
- Formula loading, update, deletion, automatic numbering, and renumbering
- Persisted complete LaTeX source, rendering options, numbering data, and formula identity
- Local vector rendering for OLE formulas
- Screenshot recognition as an official Automation API client

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
