"""Formula formatting helpers used by export actions."""

from __future__ import annotations

from io import BytesIO
import re

_MATHML_SUM = "\u2211"
_MATHML_INF = "\u221E"


def latex_to_svg(latex: str) -> str:
    """Convert a LaTeX formula to SVG with matplotlib mathtext."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 1), dpi=150)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        ax.text(0.5, 0.5, f"${latex}$", ha="center", va="center", fontsize=16, transform=ax.transAxes)

        svg_buffer = BytesIO()
        plt.savefig(svg_buffer, format="svg", bbox_inches="tight", pad_inches=0.1, facecolor="white", edgecolor="none")
        plt.close(fig)

        svg_buffer.seek(0)
        svg_str = svg_buffer.getvalue().decode("utf-8")
        return svg_str.replace('<?xml version', '<!-- SVG from matplotlib -->\n<?xml version')
    except Exception as e:
        print(f"[ERROR] LaTeX to SVG conversion failed: {e}")
        raise


def _strip_math_delimiters(latex: str) -> str:
    t = (latex or "").strip()
    if len(t) >= 4 and t.startswith("$$") and t.endswith("$$"):
        return t[2:-2].strip()
    if len(t) >= 2 and t.startswith("$") and t.endswith("$"):
        return t[1:-1].strip()
    return t


def normalize_latex_for_export(latex: str) -> str:
    """Normalize LaTeX for export by simplifying scripts and spacing common commands."""
    t = _strip_math_delimiters(latex)
    if not t:
        return ""
    t = re.sub(r"\^\{([A-Za-z0-9])\}", r"^\1", t)
    t = re.sub(r"_\{([A-Za-z0-9])\}", r"_\1", t)
    t = t.replace(":=", " := ")
    t = re.sub(r"(?<=\S)(\\(?:sum))", r" \1", t)
    t = re.sub(r"(?<=\S)(\\(?:frac|dfrac|tfrac))", r" \1", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def latex_inline(latex: str) -> str:
    return f"${latex}$"


def latex_display(latex: str) -> str:
    return f"\\[\n{latex}\n\\]"


def latex_equation(latex: str) -> str:
    return f"\\begin{{equation}}\n{latex}\n\\end{{equation}}"


def _ensure_mathml_block(mathml: str) -> str:
    if not mathml:
        return mathml
    match = re.search(r"<math\b([^>]*)>", mathml)
    if not match:
        return mathml
    attrs = match.group(1) or ""
    if re.search(r"\bdisplay\s*=", attrs):
        return mathml
    sep = " " if attrs and not attrs.endswith(" ") else ""
    new_tag = f'<math{attrs}{sep}display="block">'
    return mathml[:match.start()] + new_tag + mathml[match.end():]


def mathml_standardize(mathml: str) -> str:
    """Normalize MathML for export targets."""
    mathml = _ensure_mathml_block(mathml)
    mathml = re.sub(r"<mo>\s*:</mo>\s*<mo>\s*=\s*</mo>", "<mo>:=</mo>", mathml)
    mathml = re.sub(
        r"<mi>\s*(?:&#x221E;|&#X221E;|%s)\s*</mi>" % _MATHML_INF,
        '<mi mathvariant="normal">&#x221E;</mi>',
        mathml,
    )
    return mathml.replace(_MATHML_SUM, "&#x2211;").replace(_MATHML_INF, "&#x221E;")


def _mathml_htmlize(mathml: str) -> str:
    mathml = _ensure_mathml_block(mathml)
    mathml = re.sub(r"<mo>\s*:</mo>\s*<mo>\s*=\s*</mo>", "<mo>:=</mo>", mathml)
    mathml = re.sub(
        r"<mi>\s*(?:&#x221E;|&#X221E;|%s)\s*</mi>" % _MATHML_INF,
        f'<mi mathvariant="normal">{_MATHML_INF}</mi>',
        mathml,
    )

    def _sum_repl(match):
        attrs = match.group(1) or ""
        if "data-mjx-texclass" in attrs:
            return f"<mo{attrs}>{_MATHML_SUM}</mo>"
        sep = "" if not attrs or attrs.endswith(" ") else " "
        return f'<mo{attrs}{sep}data-mjx-texclass="OP">{_MATHML_SUM}</mo>'

    mathml = re.sub(
        r"<mo([^>]*)>\s*(?:&#x2211;|&#X2211;|%s)\s*</mo>" % _MATHML_SUM,
        _sum_repl,
        mathml,
        count=1,
    )
    mathml = mathml.replace("&#x2211;", _MATHML_SUM).replace("&#X2211;", _MATHML_SUM)
    return mathml.replace("&#x221E;", _MATHML_INF).replace("&#X221E;", _MATHML_INF)


def mathml_to_html_fragment(mathml: str) -> str:
    """Wrap MathML as an embeddable HTML fragment."""
    html_mathml = _mathml_htmlize(mathml)
    return f'<span class="latexsnipper-math" data-format="mathml">{html_mathml}</span>'


def mathml_with_prefix(mathml: str, prefix: str) -> str:
    """Add consistent namespace prefixes to MathML tags."""
    if not mathml:
        return mathml
    mathml = _ensure_mathml_block(mathml)

    def _root_repl(match):
        attrs = match.group(1) or ""
        attrs = re.sub(r'\s+xmlns="[^"]*"', "", attrs)
        if f"xmlns:{prefix}=" not in attrs:
            sep = " " if attrs and not attrs.endswith(" ") else ""
            attrs = f'{attrs}{sep}xmlns:{prefix}="http://www.w3.org/1998/Math/MathML"'
        return f"<{prefix}:math{attrs}>"

    mathml = re.sub(r"<math\b([^>]*)>", _root_repl, mathml, count=1)
    mathml = re.sub(r"</math>", f"</{prefix}:math>", mathml)

    def _tag_repl(match):
        slash, name, rest = match.group(1), match.group(2), match.group(3)
        if ":" in name:
            return match.group(0)
        return f"<{slash}{prefix}:{name}{rest}>"

    return re.sub(r"<(/?)([A-Za-z][A-Za-z0-9:.-]*)(\b[^>]*)>", _tag_repl, mathml)
