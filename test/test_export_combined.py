"""Generate combined export files: one file per format, all 25 cases in one document."""
from __future__ import annotations

import html as html_mod
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from exporting.formula_export import get_all_export_format_specs
from exporting.pandoc_exporter import check_pandoc_available, convert_latex_to, PANDOC_FORMAT_MAP

OUT_DIR = Path(__file__).resolve().parent / "export_review"
HTML_OUT = OUT_DIR / "review.html"

TEST_CASES = [
    ("01_simple", "E = mc^2"),
    ("02_fraction", r"\frac{d}{dx}\int_0^x f(t)\,dt = f(x)"),
    ("03_matrix", r"\begin{pmatrix} a & b \\ c & d \end{pmatrix} \begin{pmatrix} x \\ y \end{pmatrix} = \begin{pmatrix} ax+by \\ cx+dy \end{pmatrix}"),
    ("04_maxwell", r"\nabla \times \mathbf{E} = -\frac{\partial \mathbf{B}}{\partial t}, \quad \nabla \cdot \mathbf{B} = 0"),
    ("05_integral", r"\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}, \quad \sum_{n=0}^{\infty} \frac{x^n}{n!} = e^x"),
    ("06_nested", r"x^{y^{z^{w}}}, \quad a_{i_{j_{k}}}, \quad e^{i\pi} + 1 = 0"),
    ("07_greek", r"\alpha\beta\gamma\delta\epsilon\zeta\eta\theta\iota\kappa\lambda\mu\nu\xi\pi\rho\sigma\tau\upsilon\phi\chi\psi\omega"),
    ("08_operators", r"\sin\cos\tan\log\ln\exp\lim\sup\inf\max\min\det"),
    ("09_delimiters", r"\left( \frac{a}{b} \right), \quad \left[ \sum_{i=1}^n x_i \right], \quad \left\{ x \in \mathbb{R} : x > 0 \right\}"),
    ("10_aligned", r"\begin{aligned} f(x) &= x^2 + 2x + 1 \\ &= (x+1)^2 \end{aligned}"),
    ("11_cases", r"f(x) = \begin{cases} x^2 & \text{if } x \geq 0 \\ -x & \text{if } x < 0 \end{cases}"),
    ("12_sqrt", r"\sqrt{x}, \quad \sqrt[3]{x}, \quad \sqrt{x^2 + y^2}"),
    ("13_binomial", r"\binom{n}{k} = \frac{n!}{k!(n-k)!}, \quad \sum_{k=0}^n \binom{n}{k} = 2^n"),
    ("14_accents", r"\overline{AB}, \quad \underline{x+y}, \quad \hat{\theta}, \quad \vec{v}, \quad \dot{x}, \quad \ddot{y}"),
    ("15_euler", r"e^{i\pi} + 1 = 0"),
    ("16_text_simple", r"The famous equation $E = mc^2$ relates mass and energy."),
    ("17_text_newton", r"Newton's second law states that $F = ma$, where $F$ is force, $m$ is mass, and $a$ is acceleration."),
    ("18_text_quadratic", r"The quadratic formula $x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$ solves $ax^2 + bx + c = 0$."),
    ("19_text_integral", r"The Gaussian integral $\int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}$ is fundamental in probability theory."),
    ("20_text_maxwell", r"Maxwell's equations: $\nabla \cdot \mathbf{E} = \frac{\rho}{\epsilon_0}$ and $\nabla \times \mathbf{B} = \mu_0 \mathbf{J} + \mu_0 \epsilon_0 \frac{\partial \mathbf{E}}{\partial t}$."),
    ("21_text_euler", r"Euler's identity $e^{i\pi} + 1 = 0$ connects five fundamental constants."),
    ("22_text_pythagorean", r"The Pythagorean theorem $a^2 + b^2 = c^2$ holds for right triangles."),
    ("23_text_taylor", r"The Taylor series $e^x = \sum_{n=0}^{\infty} \frac{x^n}{n!}$ converges for all $x$."),
    ("24_text_limit", r"The definition of the derivative is $f'(x) = \lim_{h \to 0} \frac{f(x+h) - f(x)}{h}$."),
    ("25_text_mixed", r"Given $\frac{dy}{dx} = ky$ with $y(0) = y_0$, the solution is $y = y_0 e^{kx}$. This appears in population dynamics, radioactive decay, and compound interest."),
]

NATIVE_EXT = {
    "latex": ".tex", "latex_display": ".tex", "latex_equation": ".tex",
    "markdown_inline": ".md", "markdown_block": ".md",
}


def test_pandoc_file_export_is_deferred_to_worker() -> None:
    formula_export = (Path(__file__).resolve().parent.parent / "src" / "exporting" / "formula_export.py").read_text(
        encoding="utf-8"
    )
    menu = (Path(__file__).resolve().parent.parent / "src" / "ui" / "formula_export_menu.py").read_text(
        encoding="utf-8"
    )

    binary_branch = formula_export.split("if fmt.needs_file:", 1)[1].split("try:", 1)[0]
    assert 'return f"[BINARY:{format_key}]", label' in binary_branch
    assert "class _PandocFileExportWorker(QObject)" in menu
    assert "worker.moveToThread(thread)" in menu
    assert "thread.started.connect(worker.run)" in menu
    assert "convert_latex_to(self._format_key" in menu


def _esc(t):
    return html_mod.escape(str(t))


def _build_single_latex_doc():
    lines = [
        "\\documentclass[12pt]{article}",
        "\\usepackage{amsmath,amssymb,amsfonts}",
        "\\usepackage[margin=1in]{geometry}",
        "\\begin{document}",
    ]
    for name, latex in TEST_CASES:
        lines.append(f"\\section*{{{name}}}")
        lines.append(f"\\textbf{{LaTeX:}} \\verb|{latex}|")
        lines.append("")
        has_inline = "$" in latex and not latex.strip().startswith("\\[")
        if has_inline:
            lines.append(latex)
        else:
            lines.append(f"\\[{latex}\\]")
        lines.append("")
    lines.append("\\end{document}")
    return "\n".join(lines)


def main():
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    check_pandoc_available(force=True)
    generated = []
    errors = []

    # Single combined LaTeX document for pandoc
    combined_latex = _build_single_latex_doc()

    # Pandoc text formats - convert combined document
    text_pandoc_formats = [f for f in PANDOC_FORMAT_MAP.values() if not f.needs_file]
    for fmt in text_pandoc_formats:
        try:
            result = convert_latex_to(fmt.key, combined_latex, as_document=False)
            if isinstance(result, str):
                fname = f"pandoc__{fmt.key}{fmt.extension}"
                (OUT_DIR / fname).write_text(result, encoding="utf-8")
                generated.append(fname)
        except Exception as e:
            errors.append(f"pandoc/{fmt.key}: {e}")

    # Pandoc binary formats - convert combined document
    binary_pandoc_formats = [f for f in PANDOC_FORMAT_MAP.values() if f.needs_file]
    for fmt in binary_pandoc_formats:
        try:
            result = convert_latex_to(fmt.key, combined_latex, as_document=False)
            if isinstance(result, bytes):
                fname = f"pandoc__{fmt.key}{fmt.extension}"
                (OUT_DIR / fname).write_bytes(result)
                generated.append(fname)
        except Exception as e:
            errors.append(f"pandoc/{fmt.key}: {e}")

    # Native text formats - build combined
    native_specs = [s for s in get_all_export_format_specs()
                    if s.key and not s.key.startswith("_") and not s.key.startswith("pandoc_")
                    and s.key in ("latex", "latex_display", "latex_equation", "markdown_inline", "markdown_block")]
    for spec in native_specs:
        try:
            if spec.key.startswith("latex") or spec.key.startswith("markdown"):
                lines = [f"# {spec.key}\n"]
                for name, latex in TEST_CASES:
                    lines.append(f"## {name}")
                    lines.append(f"LaTeX: `{latex}`\n")
                    if spec.key == "latex":
                        lines.append(f"${latex}$")
                    elif spec.key == "latex_display":
                        lines.append(f"\\[\n{latex}\n\\]")
                    elif spec.key == "latex_equation":
                        lines.append(f"\\begin{{equation}}\n{latex}\n\\end{{equation}}")
                    elif spec.key == "markdown_inline":
                        lines.append(f"${latex}$")
                    elif spec.key == "markdown_block":
                        has_inline = "$" in latex and not latex.strip().startswith("\\[")
                        if has_inline:
                            lines.append(latex)
                        else:
                            lines.append(f"$$\n{latex}\n$$")
                    lines.append("")
                ext = NATIVE_EXT.get(spec.key, ".txt")
                fname = f"native__{spec.key}{ext}"
                (OUT_DIR / fname).write_text("\n".join(lines), encoding="utf-8")
                generated.append(fname)
        except Exception as e:
            errors.append(f"native/{spec.key}: {e}")

    # HTML index
    html_parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Export Review</title>",
        "<style>body{font-family:sans-serif;padding:20px} a{margin:4px;display:inline-block;padding:4px 8px;background:#e3f2fd;border-radius:4px;text-decoration:none;color:#1565c0} a:hover{background:#bbdefb} h2{margin-top:20px;border-bottom:1px solid #ccc;padding-bottom:4px}</style>",
        "</head><body><h1>LaTeXSnipper Export Review</h1>",
        f"<p>{len(generated)} files | 25 test cases each</p>",
    ]
    for f in sorted(generated):
        html_parts.append(f'<a href="{_esc(f)}" target="_blank">{_esc(f)}</a>')
    if errors:
        html_parts.append("<h2>Errors</h2>")
        for e in errors:
            html_parts.append(f"<p style='color:red'>{_esc(e)}</p>")
    html_parts.append("</body></html>")
    HTML_OUT.write_text("\n".join(html_parts), encoding="utf-8")

    print(f"Generated {len(generated)} files in {OUT_DIR}")
    for e in errors:
        print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
