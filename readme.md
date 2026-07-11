# LaTeXSnipper

<div align="center">

**Capture, recognize, edit, compute, and export mathematical content from one desktop workspace.**

<img width="1919" height="1020" alt="LaTeXSnipper desktop workspace" src="https://github.com/user-attachments/assets/9d00310b-d1b6-4321-b961-8837b3efb864" />

[![Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square&include_prereleases)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
[![CI](https://github.com/SakuraMathcraft/LaTeXSnipper/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/SakuraMathcraft/LaTeXSnipper/actions/workflows/ci.yml)
[![macOS CI](https://github.com/SakuraMathcraft/LaTeXSnipper/actions/workflows/macos-ci-artifact.yml/badge.svg?branch=main)](https://github.com/SakuraMathcraft/LaTeXSnipper/actions/workflows/macos-ci-artifact.yml)
[![License](https://img.shields.io/github/license/SakuraMathcraft/LaTeXSnipper?style=flat-square)](LICENSE)
[![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/stargazers)
![Platforms](https://img.shields.io/badge/Windows%20%7C%20Linux%20%7C%20macOS-supported-orange?style=flat-square)

[Download](https://github.com/SakuraMathcraft/LaTeXSnipper/releases) · [User Manual](user_manual/LaTeXSnipper_User_Manual.pdf) · [FAQ](docs/faq.md) · [Benchmarks](benchmarks/mathcraft_ocr/README.md)

English · [简体中文](README.zh-CN.md)

</div>

## Overview

LaTeXSnipper is an offline-first desktop application for mathematical OCR and document workflows. It combines screenshot, image, PDF, and handwriting recognition with a MathLive editor, live rendering, symbolic computation, history, favorites, and document export.

The built-in MathCraft OCR runtime supports three explicit result types:

| Mode | Intended input | Result and rendering |
|---|---|---|
| Formula | Isolated formulas and derivations | LaTeX formula |
| Mixed | Mathematical pages with text and formulas | Markdown with LaTeX math |
| Text | Plain text regions | Plain text |

External visual models can use the same three result contracts through Ollama or OpenAI-compatible APIs. MinerU Local is supported through its native document parsing API.

## Quick Start

1. Download the package for your platform from [GitHub Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases).
2. Start LaTeXSnipper and open the dependency wizard when prompted.
3. Install the required runtime layers. `BASIC + CORE + MATHCRAFT_CPU` is the stable default; use `MATHCRAFT_GPU` on a supported NVIDIA setup.
4. Trigger screenshot recognition from the main window or the global shortcut, then edit, copy, save, or export the result.

Windows releases include a minimal Python 3.11 dependency runtime. Linux and macOS create the optional dependency environment from a system Python `>=3.10,<3.13`; Python 3.11 is recommended. Detailed installation and troubleshooting guidance is available in the [user manual](user_manual/LaTeXSnipper_User_Manual.pdf).

## Core Capabilities

| Area | Capabilities |
|---|---|
| Recognition | Screenshot, image, PDF page ranges, handwriting, formula/text/mixed modes |
| Editing | MathLive visual editor, virtual keyboard, live MathJax preview, multiline formulas |
| Computation | Evaluate, simplify, numeric evaluate, expand, factor, and solve |
| Knowledge flow | Typed history and favorites with stable rendering metadata |
| External models | Ollama, OpenAI-compatible visual APIs, and MinerU Local |
| Export | 20 formats spanning LaTeX, Markdown, MathML, HTML, OMML, SVG, Office documents, EPUB, PDF, Typst, and text |
| Desktop integration | Global shortcut, system tray/menu bar, clipboard and multi-display capture |

Recognition and computation can remain local. External services are optional and configured explicitly by the user.

## Reproducible Benchmarks

MathCraft OCR includes a source-controlled benchmark suite with manifests, runners, metric scripts, protocol notes, and compact result reports. Large public datasets and prediction dumps remain outside the repository.

| Benchmark | Scale | Reported result | Purpose |
|---|---:|---|---|
| UniMER-Test | 23,757 formulas | BLEU-4 `0.7946`; official CDM `0.9288` on 23,701 render-evaluable samples | Printed and handwritten formula OCR |
| MathWriting test | 7,644 samples | BLEU-4 `0.5467`; official CDM `0.750`; prediction render success `98.63%` | Independent handwriting stress test |
| OpenStax mixed pages | 200 pages | `0` failures, `0` empty outputs; median latency `6.65 s/page` | Mixed-page completion, structure, and runtime |

All recorded runs used `CUDAExecutionProvider`; latency is hardware-dependent. The datasets serve different evaluation roles, so the rows are not a model-ranking comparison. See the [benchmark protocol and reproduction guide](benchmarks/mathcraft_ocr/README.md), the checked-in [result reports](benchmarks/mathcraft_ocr/results), and the model repository's [published tables and charts](https://github.com/SakuraMathcraft/MathCraft-Models/tree/main/benchmarks).

## Microsoft Office Plugin

The released Windows plugin integrates LaTeXSnipper with desktop Word and PowerPoint:

- Word OLE and native OMML formula insertion
- PowerPoint OLE and high-DPI PNG insertion
- Shared MathLive formula editor and symbol library
- Formula loading, update, deletion, numbering, and renumbering
- Persistent source, rendering, numbering, and formula identity metadata
- Screenshot OCR through the local desktop bridge

Download `OfficePluginSetup-<version>.exe` from [Releases](https://github.com/SakuraMathcraft/LaTeXSnipper/releases). It supports 32-bit and 64-bit desktop Office 2019, 2021, 2024, LTSC 2021/2024, and Microsoft 365 Apps on Windows. See the [Office plugin documentation](office_plugin/README.md).

## Export Formats

Built-in exports do not require Pandoc:

- LaTeX inline, display, and equation
- Markdown inline and block math
- MathML standard, `.mml`, `<m>`, and attribute forms
- HTML, Word OMML, and SVG source

The optional `PANDOC` layer enables Word `.docx`, ODT `.odt`, PowerPoint `.pptx`, EPUB `.epub`, PDF `.pdf`, standalone HTML, Typst, and plain text. Complete SVG blocks in document content are validated, rendered, and embedded as image assets for document exports. PDF export additionally requires a usable LaTeX PDF engine.

## Platform Support

| Platform | Packaging | Integration notes |
|---|---|---|
| Windows | Per-user Inno installer | Native global shortcut, tray integration, bundled minimal Python runtime |
| Linux | Debian package | `pynput` shortcut provider; Qt capture with optional Wayland/X11 or portal tools |
| macOS | `.app.zip` and DMG | Native shortcut provider, Dock/menu integration, Screen Recording permission for capture |

Application state, logs, dependency environments, shared tools, temporary files, and model weights follow platform-specific user-data locations documented in [User Data Storage](docs/user_data_storage.md).

## Star History

<a href="https://repostars.dev/?repos=SakuraMathcraft%2FLaTeXSnipper">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://repostars.dev/api/embed?repo=SakuraMathcraft%2FLaTeXSnipper&amp;theme=dark">
    <source media="(prefers-color-scheme: light)" srcset="https://repostars.dev/api/embed?repo=SakuraMathcraft%2FLaTeXSnipper&amp;theme=light">
    <img alt="LaTeXSnipper star history chart" src="https://repostars.dev/api/embed?repo=SakuraMathcraft%2FLaTeXSnipper&amp;theme=light">
  </picture>
</a>

## Supporters

Thanks to everyone who supports development, testing, documentation, and community maintenance.

| Supporter | Contribution |
|---|---|
| [strangelion](https://github.com/strangelion) | Contributor |
| [Galileo927](https://github.com/Galileo927) | Contributor |
| [ljygo](https://github.com/ljygo) | Sponsor |
| [Yokie-D](https://github.com/Yokie-D) | Sponsor |

## Support the Project

LaTeXSnipper is free, open-source, ad-free, and maintained as an independent project. Sponsorship, issue reports, reproducible tests, and documentation contributions help sustain long-term maintenance.

| Alipay | WeChat | Community group |
|---|---|---|
| <img width="240" alt="Alipay" src="https://github.com/user-attachments/assets/1efa46b7-07cb-4a3e-821d-f23b7a36ab34" /> | <img width="240" alt="WeChat" src="https://github.com/user-attachments/assets/19065b1d-ac40-478e-8318-fabb75488c5c" /> | <img width="240" alt="LaTeXSnipper community group" src="https://github.com/user-attachments/assets/91c30d59-a4a7-4118-b24b-dada0fe002bf" /> |

## License

LaTeXSnipper is licensed under the [GNU General Public License v3.0](LICENSE).
