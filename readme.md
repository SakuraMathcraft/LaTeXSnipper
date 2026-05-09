# LaTeXSnipper ✨

<div align="center">

> A desktop math workspace for **capture -> recognize -> handwrite -> edit -> compute**
<img width="1919" height="1018" alt="主界面-浅色" src="https://github.com/user-attachments/assets/54561c3b-1a60-438a-b8f0-6c6419674b8f" />

![Stars](https://img.shields.io/github/stars/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Stars&color=FFD700)
![Forks](https://img.shields.io/github/forks/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Forks&color=1f6feb)
![Issues](https://img.shields.io/github/issues/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Issues&color=d1481e)
![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)
![Version](https://img.shields.io/badge/version-v2.3.2-brightgreen?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows-orange?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11-blue?style=flat-square)

[![GitHub Release](https://img.shields.io/github/v/release/SakuraMathcraft/LaTeXSnipper?style=flat-square&include_prereleases)](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
[![Last Commit](https://img.shields.io/github/last-commit/SakuraMathcraft/LaTeXSnipper?style=flat-square)](https://github.com/SakuraMathcraft/LaTeXSnipper/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/SakuraMathcraft/LaTeXSnipper?style=flat-square&label=Activity)](https://github.com/SakuraMathcraft/LaTeXSnipper/graphs/commit-activity)

### Star History

[![Star History Chart](https://api.star-history.com/svg?repos=SakuraMathcraft/LaTeXSnipper&type=Date)](https://star-history.com/#SakuraMathcraft/LaTeXSnipper&Date)

</div>

---

## Overview

**LaTeXSnipper** is no longer just a "screenshot formula -> LaTeX" utility.
It is a desktop workspace built for end-to-end math content workflows:

- Capture and recognize mathematical content from screenshots
- Continue editing and computing in the integrated math workbench
- Handwrite expressions in a dedicated canvas and convert to LaTeX
- Send results back to the main editor or copy to clipboard

---

## Feature Walkthrough

### Math Workbench

<img width="1308" height="834" alt="数学工作台-暗色" src="https://github.com/user-attachments/assets/320a84b3-293d-4947-bc95-fbac88b1f664" />

The `v2.0` Math Workbench supports a complete workflow:

1. Capture and recognize formulas from the main window
2. Load results into the workbench in one click
3. Edit expressions in the `MathLive` area
4. Use the virtual math keyboard for fractions, superscripts, integrals, series, and more
5. Run `Compute / Simplify / Numeric / Expand / Factor / Solve`
6. Write results back to the editor or copy as LaTeX / MathJSON

### Auto Typesetting Document Window

<img width="1919" height="1014" alt="v2 3深色" src="https://github.com/user-attachments/assets/c6dffd39-26d9-4e54-aba9-a4b010d3603e" />

The `v2.3.2` Auto Typesetting Document Window supports source-level editing with synchronized preview:

1. Open "Auto Typesetting" from the handwriting window
2. Edit full source in the left `TeX Document` pane
3. Insert complex expressions with the built-in formula editor
4. Compile and preview PDF directly
5. Navigate bi-directionally between source and PDF via SyncTeX
6. Export `.tex` or `PDF` when needed

### Handwriting Recognition

<img width="1408" height="916" alt="手写识别readme" src="https://github.com/user-attachments/assets/3fe98e41-218e-452c-96c1-cc805ab3e0f2" />

The `v2.1` handwriting window supports the following flow:

1. Open "Handwriting Recognition" from the main window
2. Write formulas directly on an isolated canvas
3. Trigger MathCraft OCR automatically after pen-up
4. See live `LaTeX output` and rendered preview on the right
5. Copy LaTeX directly or insert it back into the main editor

---

## Core Features

| Feature | Description |
|------|------|
| 📸 Formula recognition | MathCraft OCR for formulas, text, and mixed content |
| ✍️ Handwriting recognition | Dedicated handwriting window with auto-recognition and live preview |
| 🧮 Math workbench | Separate workspace for editing, computation, and write-back |
| ⌨️ Formula editing | Integrated `MathLive math-field` with virtual math keyboard |
| 🔄 Multi-format export | 30 export choices across LaTeX, Markdown, MathML, HTML, OMML, SVG, Typst, Word, EPUB, RTF, wiki formats, and more |
| 📐 Core computation | Compute, simplify, numeric evaluate, expand, factor, solve |
| 🧠 Advanced fallback | Local `SymPy/mpmath` engine for harder expressions |
| 🌙 Theme support | Light/Dark adaptation across windows and tools |
| 🔐 Offline-first | Recognition and advanced solving can run locally for privacy |

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

For heavy expressions, the engine uses automatic fallback:

1. Try frontend `Compute Engine` first
2. Switch to local advanced engine on timeout/failure/unreliable results
3. Use `SymPy/mpmath` for robust fallback
4. Recover closed forms for selected known constants from numeric output

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

Pandoc is optional. If it is not installed, the core recognition, editing, handwriting, preview, and built-in export formats continue to work normally.

---

## Quick Start

### Option 1: Download the executable

1. Visit the [Releases page](https://github.com/SakuraMathcraft/LaTeXSnipper/releases)
2. Download the latest `LaTeXSnipper Final Stable.exe`
3. Run the installer
4. Complete environment setup via the dependency wizard on first launch
5. Start capturing, handwriting, or using the math workbench

### Option 2: Run from source

```bash
git clone https://github.com/SakuraMathcraft/LaTeXSnipper.git
cd LaTeXSnipper

python -m venv .venv
.\.venv\Scripts\activate

pip install -r requirements.txt
python src/main.py
```

---

## Project Structure

```text
LaTeXSnipper/
|-- mathcraft_ocr/                 # Standalone MathCraft OCR runtime and CLI
|-- src/
|   |-- main.py                    # Main desktop application entry
|   |-- distribution.py            # GitHub / Microsoft Store channel policy
|   |-- backend/                   # OCR wrapper, CUDA diagnostics, capture, platform services
|   |-- bootstrap/                 # Dependency wizard and runtime verification
|   |-- core/                      # Document composition, export contracts, restart contracts
|   |-- editor/                    # Math workbench and formula editing UI
|   |-- handwriting/               # Handwriting canvas, PDF preview, document tools
|   |-- preview/                   # MathJax preview and render helpers
|   |-- runtime/                   # Config, history, and runtime helpers
|   |-- ui/                        # Extracted desktop dialogs and window helpers
|   |-- assets/                    # Icons and bundled web/math resources
|   `-- deps/                      # Bundled/local Python dependency environment
|-- Inno/                          # GitHub Release installer scripts
|-- packaging/msix/                # Microsoft Store MSIX manifest and notes
|-- scripts/                       # Build, release, and regression utilities
|-- docs/                          # Design and architecture notes
|-- LaTeXSnipper.spec              # PyInstaller GitHub build
|-- LaTeXSnipper.offline.spec      # PyInstaller offline-model build
|-- pyproject.toml
|-- requirements.txt
|-- requirements-build.txt
|-- version_info.txt
`-- README.md
```

---

## Contributing

Contributions are welcome:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push your branch
5. Open a Pull Request

Recommended focus areas:

- Handwriting UX
- Math workbench UX
- Advanced solver stability
- Packaged runtime verification
- Theme consistency across windows

---

## License

This project is open-sourced under the [MIT License](LICENSE).

---

## Acknowledgements

Special thanks to:

- [pix2tex](https://github.com/lukas-blecher/LaTeX-OCR)
- [MathLive](https://github.com/arnog/mathlive)
- [MathLive Compute Engine](https://mathlive.io/compute-engine/)
- [SymPy](https://www.sympy.org/)
- [mpmath](https://mpmath.org/)
- [MathJax](https://www.mathjax.org/)
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/)
- [QFluentWidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)

---

<div align="center">

| Download | Issues | Discussions | Wiki |
|---|---|---|---|
| [Latest Release](https://github.com/SakuraMathcraft/LaTeXSnipper/releases/latest) | [Open an Issue](https://github.com/SakuraMathcraft/LaTeXSnipper/issues) | [Discussions](https://github.com/SakuraMathcraft/LaTeXSnipper/discussions) | [Project Wiki](https://github.com/SakuraMathcraft/LaTeXSnipper/wiki) |

</div>
