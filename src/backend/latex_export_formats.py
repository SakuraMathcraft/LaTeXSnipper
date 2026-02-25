import os
import re


_MATHML_SUM = "\u2211"
_MATHML_INF = "\u221E"


def _strip_math_delimiters(latex: str) -> str:
    text = (latex or "").strip()
    if len(text) >= 4 and text.startswith("$$") and text.endswith("$$"):
        return text[2:-2].strip()
    if len(text) >= 2 and text.startswith("$") and text.endswith("$"):
        return text[1:-1].strip()
    return text


def normalize_latex_for_export(latex: str) -> str:
    text = _strip_math_delimiters(latex)
    if not text:
        return ""
    text = re.sub(r"\^\{([A-Za-z0-9])\}", r"^\1", text)
    text = re.sub(r"_\{([A-Za-z0-9])\}", r"_\1", text)
    text = text.replace(":=", " := ")
    text = re.sub(r"(?<=\S)(\\(?:sum))", r" \1", text)
    text = re.sub(r"(?<=\S)(\\(?:frac|dfrac|tfrac))", r" \1", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


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
    new_tag = f"<math{attrs}{sep}display=\"block\">"
    return f"{mathml[:match.start()]}{new_tag}{mathml[match.end():]}"


def mathml_standardize(mathml: str) -> str:
    value = _ensure_mathml_block(mathml)
    value = re.sub(r"<mo>\s*:</mo>\s*<mo>\s*=\s*</mo>", "<mo>:=</mo>", value)
    value = re.sub(
        r"<mi>\s*(?:&#x221E;|&#X221E;|%s)\s*</mi>" % _MATHML_INF,
        '<mi mathvariant="normal">&#x221E;</mi>',
        value,
    )
    value = value.replace(_MATHML_SUM, "&#x2211;").replace(_MATHML_INF, "&#x221E;")
    return value


def mathml_with_prefix(mathml: str, prefix: str) -> str:
    if not mathml:
        return mathml
    value = _ensure_mathml_block(mathml)

    def _root_repl(match: re.Match[str]) -> str:
        attrs = match.group(1) or ""
        attrs = re.sub(r'\s+xmlns="[^"]*"', "", attrs)
        if f"xmlns:{prefix}=" not in attrs:
            sep = " " if attrs and not attrs.endswith(" ") else ""
            attrs = f'{attrs}{sep}xmlns:{prefix}="http://www.w3.org/1998/Math/MathML"'
        return f"<{prefix}:math{attrs}>"

    value = re.sub(r"<math\b([^>]*)>", _root_repl, value, count=1)
    value = re.sub(r"</math>", f"</{prefix}:math>", value)

    def _tag_repl(match: re.Match[str]) -> str:
        slash, name, rest = match.group(1), match.group(2), match.group(3)
        if ":" in name:
            return match.group(0)
        return f"<{slash}{prefix}:{name}{rest}>"

    return re.sub(r"<(/?)([A-Za-z][A-Za-z0-9:.-]*)(\b[^>]*)>", _tag_repl, value)


def latex_to_mathml(latex: str) -> str:
    import latex2mathml.converter

    clean = normalize_latex_for_export(latex)
    out = latex2mathml.converter.convert(clean)
    return mathml_standardize(out)


def latex_to_omml(latex: str) -> str:
    clean = normalize_latex_for_export(latex)
    mathml = latex_to_mathml(clean)
    try:
        from lxml import etree
    except Exception:
        return mathml

    xsl_paths = [
        os.path.expandvars(r"%ProgramFiles%\Microsoft Office\root\Office16\MML2OMML.XSL"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\MML2OMML.XSL"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office16\MML2OMML.XSL"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft Office\Office19\MML2OMML.XSL"),
    ]
    xsl_path = ""
    for path in xsl_paths:
        if os.path.exists(path):
            xsl_path = path
            break
    if not xsl_path:
        return mathml
    try:
        xsl_doc = etree.parse(xsl_path)
        transform = etree.XSLT(xsl_doc)
        mathml_doc = etree.fromstring(mathml.encode("utf-8"))
        omml_doc = transform(mathml_doc)
        value = etree.tostring(omml_doc, encoding="unicode")
        return value or mathml
    except Exception:
        return mathml


def build_export_formats(latex: str) -> tuple[dict[str, str], dict[str, str]]:
    result = str(latex or "").strip()
    formats: dict[str, str] = {
        "latex": result,
        "markdown": f"$$\n{result}\n$$\n" if result else "",
    }
    errors: dict[str, str] = {}
    if not result:
        return formats, errors

    try:
        base_mathml = latex_to_mathml(result)
        formats["mathml"] = base_mathml
        formats["mathml_mml"] = mathml_with_prefix(base_mathml, "mml")
        formats["mathml_m"] = mathml_with_prefix(base_mathml, "m")
        formats["mathml_attr"] = mathml_with_prefix(base_mathml, "attr")
    except Exception as exc:
        errors["mathml"] = str(exc)
        errors["mathml_mml"] = str(exc)
        errors["mathml_m"] = str(exc)
        errors["mathml_attr"] = str(exc)

    try:
        formats["omml"] = latex_to_omml(result)
    except Exception as exc:
        errors["omml"] = str(exc)

    return formats, errors
