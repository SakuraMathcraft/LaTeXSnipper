# LaTeXSnipper ✨

<div align="center">

Turn screenshots, images, PDFs, and handwriting into editable formulas and text.

[![GitHub Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest)
![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Stars&color=FFD700)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-orange?style=flat-square)
![License](https://img.shields.io/badge/license-GPLv3-blue?style=flat-square)

**[Download](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest)** · [User Manual (Chinese PDF)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest/download/LaTeXSnipper_User_Manual.pdf) · [FAQ](docs/faq.md) · [Demos](#demos)

English · [简体中文](README.zh-CN.md)

<img width="960" alt="LaTeXSnipper v3.0.0: recognition history, formula editor, and live preview" src="docs/latexsnipper-3.0.0.png" />

</div>

## What You Can Do

| Feature | What it offers |
|---|---|
| 📸 Recognize | Capture a region, open an image, select PDF pages, or write by hand; recognize formulas, text, and mixed content |
| ⌨️ Edit and compute | Edit with MathLive and live preview; simplify, evaluate, and solve in the math workspace |
| 🔄 Export | Copy formulas or export documents in 20 formats, including LaTeX, MathML, Word, PDF, and Typst |
| 🧩 Integrate | Work in Word/PowerPoint or connect scripts and other tools through the Automation API |
| 🔐 Choose your model | Run MathCraft OCR locally after downloading dependencies and weights, or configure a local/online external model |
| 🌐 Make it yours | English/Chinese interface, light/dark themes, configurable shortcuts, history, and favorites |

MathCraft OCR: [benchmark results](https://github.com/SakuraMathcraft/MathCraft-Models/tree/main/benchmarks) · [reproduce the benchmarks](benchmarks/mathcraft_ocr/README.md)

## Download and Get Started

1. **Install the desktop app.** Choose the package for your system from [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest).
2. **Prepare recognition.** On first launch, use Dependency Management to install the required layers and a CPU or GPU backend for MathCraft OCR. Initial model setup requires downloading weights. If using only an external model, configure and test its connection in Settings instead.
3. **Recognize and edit.** Use Capture Recognize, Image, PDF, or Handwriting, then review, copy, or export the result.

| Platform | Download | Before using recognition |
|---|---|---|
| Windows | `LaTeXSnipperSetup-<version>.exe` | Python runtime included; no separate system Python installation needed |
| Linux (Debian/Ubuntu) | `.deb` for your architecture | Python `>=3.10,<3.14` with venv/pip; Wayland may restrict screenshots and global shortcuts |
| macOS | `.dmg` or `.app.zip` for your architecture | Python `>=3.10,<3.14` with venv/pip; grant Screen Recording permission for screenshots |

Linux/macOS use system Python to create the managed dependency environment; Windows uses its bundled Python 3.11 template. The `.deb` declares `python3` and `python3-venv` dependencies. On macOS, install a supported Python version if one is not available.

For permissions, model downloads, environment paths, and troubleshooting, see the [FAQ](docs/faq.md), [user data locations](docs/user_data_storage.md), and [full user manual (Chinese PDF)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest/download/LaTeXSnipper_User_Manual.pdf).

## Demos

### Screenshot Recognition

![Screenshot recognition demo](docs/demos/screenshot-recognition.gif)

<details>
<summary>Image Recognition — view demo</summary>

![Image recognition demo](docs/demos/image-recognition.gif)

</details>

<details>
<summary>PDF Recognition — view demo</summary>

![PDF recognition demo](docs/demos/pdf-recognition.gif)

</details>

## Microsoft Office Plugin

Insert and edit formulas directly in Windows desktop Word and PowerPoint:

- Word OLE/OMML and PowerPoint OLE/PNG insertion, with editable LaTeX source.
- Formula editing, updates, and Word automatic numbering and references.
- Local formula rendering and screenshot OCR through the desktop Automation API.

Download `OfficePluginSetup-<version>.exe` separately from [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest). Supports 32-bit and 64-bit Office 2019/2021/2024, LTSC 2021/2024, and Microsoft 365 Apps on Windows.

[Installation requirements and features](office_plugin/README.md) · [Formula workflows](docs/office_plugin_formula_workflows.md)

## Automation API

Use MathCraft or your configured external model from scripts, batch jobs, editor integrations, or authorized remote devices.

- **Desktop shortcuts:** connect Snipaste, AutoHotkey, AutoKey, Hammerspoon, or ShareX to an image-recognition workflow.
- **Batch and editor workflows:** submit images with Python/curl and insert results into your tools.
- **Mobile access:** connect Shortcuts or Tasker to your running desktop app through a secure tunnel.

The API is **disabled by default**. Local clients use the address and token in `automation-api.json`. Remote access requires explicit opt-in, a separate key, and HTTPS or an encrypted tunnel; do not expose it over plain public HTTP. Remote external-model access is separately controlled and may incur provider charges.

[API reference and connection setup](docs/automation_api.md) · [Ready-to-adapt client examples](examples/automation/README.md)

## Export

Built-in exports cover LaTeX, Markdown math, MathML, HTML, Word OMML, and SVG code. Install the optional **Pandoc** layer in Dependency Management for document exports such as Word, PowerPoint, EPUB, PDF, and Typst. PDF export also requires a LaTeX PDF engine.

See the [user manual](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest/download/LaTeXSnipper_User_Manual.pdf) for the full format list and requirements.

## Supporters

Thanks to everyone who helps with development, testing, documentation, and community support.

| Supporter | Contribution |
|---|---|
| [strangelion](https://github.com/strangelion) | Contributor |
| [Galileo927](https://github.com/Galileo927) | Contributor |
| [ljygo](https://github.com/ljygo) | Sponsor |
| [Yokie-D](https://github.com/Yokie-D) | Sponsor |

## Support the Project

LaTeXSnipper is a free, open-source, ad-free personal project with no in-app purchases. If it helps your work, consider starring the repository, sharing it, [reporting an issue](https://github.com/SakuraMathcraft/LaTeXSnipper/issues), or sponsoring maintenance.

[LINUX DO Community](https://linux.do/)

<details>
<summary>Sponsorship and community QR codes</summary>

| Alipay | WeChat Pay | Community chat (Chinese) |
|---|---|---|
| <img width="240" alt="Alipay donation QR code" src="https://github.com/user-attachments/assets/1efa46b7-07cb-4a3e-821d-f23b7a36ab34" /> | <img width="240" alt="WeChat Pay donation QR code" src="https://github.com/user-attachments/assets/19065b1d-ac40-478e-8318-fabb75488c5c" /> | <img width="240" alt="LaTeXSnipper community chat QR code" src="https://github.com/user-attachments/assets/91c30d59-a4a7-4118-b24b-dada0fe002bf" /> |

</details>

## License

[GNU General Public License v3](LICENSE).
