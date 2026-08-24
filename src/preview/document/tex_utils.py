from __future__ import annotations

import re


DOCUMENT_CLASS = r"\documentclass[UTF8]{ctexart}"
REQUIRED_PREAMBLE_LINES = (
    r"\usepackage{amsmath,amssymb,amsthm,mathtools,bm}",
    r"\usepackage{geometry}",
    r"\usepackage{graphicx}",
    r"\usepackage{booktabs}",
    r"\usepackage{array}",
    r"\usepackage{multirow}",
    r"\geometry{a4paper,margin=2.2cm}",
)
_REQUIRED_PACKAGES = {
    "amsmath",
    "amssymb",
    "amsthm",
    "mathtools",
    "bm",
    "geometry",
    "graphicx",
    "booktabs",
    "array",
    "multirow",
}
_DOCUMENT_CLASS_RE = re.compile(r"\\documentclass(?:\[[^\]]*])?\{[^{}]+}")
_USEPACKAGE_RE = re.compile(r"\\usepackage(?:\[[^\]]*])?\{([^{}]+)}")
_DISPLAY_DOLLAR_RE = re.compile(r"\$\$(.*?)\$\$", flags=re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\$(?:\\.|[^$])+\$")


WRAP_ENVIRONMENTS = {
    "行内公式 $...$": ("inline", "$", "$"),
    "行间公式 \\[...\\]": ("display", r"\[", r"\]"),
    "equation": ("equation", r"\begin{equation}", r"\end{equation}"),
    "equation*": ("equation*", r"\begin{equation*}", r"\end{equation*}"),
    "align": ("align", r"\begin{align}", r"\end{align}"),
    "align*": ("align*", r"\begin{align*}", r"\end{align*}"),
    "multline": ("multline", r"\begin{multline}", r"\end{multline}"),
    "multline*": ("multline*", r"\begin{multline*}", r"\end{multline*}"),
}


def sanitize_tex_templates(text: str) -> str:
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not value:
        return ""
    value = re.sub(r"\\placeholder\{([^{}]*)\}", r" {\1} ", value)
    value = re.sub(r"(?<!\\)placeholder\{([^{}]*)\}", r" {\1} ", value)
    value = re.sub(r"_\{\}", "", value)
    value = re.sub(r"\^\{\}", "", value)
    value = re.sub(r"\\!\s*\\mathrm\{d\}", r"\\,\\mathrm{d}", value)
    value = _DISPLAY_DOLLAR_RE.sub(lambda match: _display_dollars_to_latex(match.group(1)), value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    return value.rstrip()


def _display_dollars_to_latex(body: str) -> str:
    content = str(body or "").strip()
    if not content:
        return ""
    return "\n\\[\n" + content + "\n\\]\n"


def normalize_document_preamble(preamble: str) -> str:
    raw_lines = str(preamble or "").replace("\r\n", "\n").replace("\r", "\n").splitlines()
    preserved: list[str] = []
    for raw_line in raw_lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if _DOCUMENT_CLASS_RE.fullmatch(stripped):
            continue
        package_match = _USEPACKAGE_RE.fullmatch(stripped)
        if package_match:
            package_names = {
                item.strip()
                for item in package_match.group(1).split(",")
                if item.strip()
            }
            if package_names and package_names.issubset(_REQUIRED_PACKAGES):
                continue
        if stripped.startswith(r"\geometry{"):
            continue
        preserved.append(line)

    lines = [DOCUMENT_CLASS, *REQUIRED_PREAMBLE_LINES]
    for line in preserved:
        if line not in lines:
            lines.append(line)
    return "\n".join(lines).strip()


def looks_like_naked_formula_line(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped or stripped.startswith("%"):
        return False
    if re.search(r"\$[^$]+\$", stripped) or re.search(r"\\\([^)]*\\\)", stripped):
        return False
    if stripped.startswith("$") and stripped.endswith("$"):
        return False
    if any(token in stripped for token in (r"\[", r"\]", "$$", r"\(", r"\)")):
        return False
    if any(
        stripped.startswith(prefix)
        for prefix in (
            "#",
            "-",
            "*",
            r"\item",
            r"\section",
            r"\subsection",
            r"\paragraph",
            r"\chapter",
            r"\documentclass",
            r"\usepackage",
            r"\geometry",
            r"\title",
            r"\author",
            r"\date",
        )
    ):
        return False
    has_math_marker = bool(re.search(r"(\\[A-Za-z]+|[_^=<>]|[+\-*/]|[{}])", stripped))
    if not has_math_marker:
        return False
    plain_words = re.findall(r"[A-Za-z]{3,}", stripped)
    if plain_words and not re.search(r"\\[A-Za-z]+|[_^=<>]", stripped):
        return False
    return True


def normalize_document_body(text: str) -> str:
    lines = str(text or "").splitlines()
    normalized: list[str] = []
    in_math_block = False
    for raw_line in lines:
        line = sanitize_tex_templates(raw_line.rstrip())
        stripped = line.strip()
        if stripped in (r"\[", r"\]"):
            normalized.append(stripped)
            in_math_block = stripped == r"\["
            continue
        if stripped.startswith(r"\begin{"):
            in_math_block = True
            normalized.append(line)
            continue
        if stripped.startswith(r"\end{"):
            normalized.append(line)
            in_math_block = False
            continue
        if in_math_block or not looks_like_naked_formula_line(stripped):
            normalized.append(line)
            continue
        normalized.extend([r"\[", stripped, r"\]"])
    return preserve_plain_text_line_breaks("\n".join(normalized)).strip()


def preserve_plain_text_line_breaks(text: str) -> str:
    """Make source line breaks between ordinary text lines visible after TeX compilation."""
    lines = str(text or "").splitlines()
    result: list[str] = []
    in_math_block = False
    previous_was_text = False
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        starts_math = _starts_display_math_block(stripped)
        ends_math = _ends_display_math_block(stripped)
        is_text = (not in_math_block) and _is_ordinary_document_text_line(stripped)
        if is_text and previous_was_text and result and result[-1] != "":
            result.append("")
        result.append(line)
        if starts_math:
            in_math_block = True
        if ends_math:
            in_math_block = False
        previous_was_text = is_text
    return "\n".join(result).strip()


def _starts_display_math_block(line: str) -> bool:
    return (
        line == r"\["
        or line.startswith(r"\begin{equation")
        or line.startswith(r"\begin{align")
        or line.startswith(r"\begin{gather")
        or line.startswith(r"\begin{multline")
        or line.startswith(r"\begin{cases")
        or line.startswith(r"\begin{matrix")
        or line.startswith(r"\begin{pmatrix")
        or line.startswith(r"\begin{bmatrix")
    )


def _ends_display_math_block(line: str) -> bool:
    return (
        line == r"\]"
        or line.startswith(r"\end{equation")
        or line.startswith(r"\end{align")
        or line.startswith(r"\end{gather")
        or line.startswith(r"\end{multline")
        or line.startswith(r"\end{cases")
        or line.startswith(r"\end{matrix")
        or line.startswith(r"\end{pmatrix")
        or line.startswith(r"\end{bmatrix")
    )


def _is_ordinary_document_text_line(line: str) -> bool:
    if not line or line.startswith("%"):
        return False
    if line.startswith("\\"):
        return False
    return not looks_like_naked_formula_line(line)


def merge_layout_with_recognized_draft(layout_text: str, draft_text: str) -> str:
    """Keep ordinary text from the OCR draft when an external layout model drops it."""
    wrapped = wrap_tex_document(layout_text)
    draft_lines = _ordinary_text_lines(draft_text)
    if not wrapped or not draft_lines:
        return wrapped

    begin_token = r"\begin{document}"
    end_token = r"\end{document}"
    begin_idx = wrapped.find(begin_token)
    end_idx = wrapped.rfind(end_token)
    if begin_idx < 0 or end_idx <= begin_idx:
        return wrapped

    body_start = begin_idx + len(begin_token)
    body = wrapped[body_start:end_idx].strip()
    existing_lines = _ordinary_text_lines(body)
    existing_norms = [_compare_text_line(line) for line in existing_lines]
    missing = [
        line
        for line in draft_lines
        if not _draft_line_is_preserved(line, existing_norms)
    ]
    if not missing:
        return wrapped

    body = _remove_superseded_text_lines(body, missing)
    merged_body = preserve_plain_text_line_breaks("\n".join([*missing, body]).strip())
    return f"{wrapped[:body_start].rstrip()}\n{merged_body}\n{wrapped[end_idx:].strip()}".strip()


def _ordinary_text_lines(text: str) -> list[str]:
    lines: list[str] = []
    in_math_block = False
    for raw_line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("$$") or line == r"\[" or line.startswith(r"\begin{equation") or line.startswith(r"\begin{align") or line.startswith(r"\begin{gather") or line.startswith(r"\begin{multline"):
            in_math_block = True
            continue
        if line.endswith("$$") or line == r"\]" or line.startswith(r"\end{equation") or line.startswith(r"\end{align") or line.startswith(r"\end{gather") or line.startswith(r"\end{multline"):
            in_math_block = False
            continue
        if in_math_block:
            continue
        if line.startswith("\\") or looks_like_naked_formula_line(line):
            continue
        cleaned = _INLINE_MATH_RE.sub("", line).strip()
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def _compare_text_line(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).casefold()


def _draft_line_is_preserved(draft_line: str, existing_norms: list[str]) -> bool:
    draft_norm = _compare_text_line(draft_line)
    if not draft_norm:
        return True
    return any(draft_norm == existing or draft_norm in existing for existing in existing_norms)


def _remove_superseded_text_lines(body: str, replacement_lines: list[str]) -> str:
    replacement_norms = [_compare_text_line(line) for line in replacement_lines]
    kept: list[str] = []
    for raw_line in str(body or "").splitlines():
        line = raw_line.strip()
        line_norm = _compare_text_line(line)
        if line_norm and any(
            line_norm != replacement and line_norm in replacement
            for replacement in replacement_norms
        ):
            continue
        kept.append(raw_line)
    return "\n".join(kept).strip()


def wrap_tex_document(text: str) -> str:
    content = sanitize_tex_templates(str(text or "")).strip()
    if not content:
        return ""
    if "\\documentclass" in content and "\\begin{document}" in content and "\\end{document}" in content:
        begin_idx = content.find("\\begin{document}")
        end_idx = content.rfind("\\end{document}")
        if begin_idx >= 0 and end_idx > begin_idx:
            begin_token = "\\begin{document}"
            preamble = normalize_document_preamble(content[:begin_idx].strip())
            body = content[begin_idx + len(begin_token): end_idx].strip()
            normalized_body = normalize_document_body(body) or "% TODO: 补全文档正文"
            return f"{preamble}\n\n\\begin{{document}}\n{normalized_body}\n\\end{{document}}".strip()
        return content

    if "\\documentclass" in content:
        if "\\begin{document}" in content and "\\end{document}" not in content:
            return wrap_tex_document(content + "\n\\end{document}")
        if "\\begin{document}" not in content:
            lines = content.splitlines()
            preamble_lines: list[str] = []
            body_lines: list[str] = []
            in_preamble = True
            for line in lines:
                stripped = line.strip()
                if in_preamble and (
                    not stripped
                    or stripped.startswith("%")
                    or stripped.startswith("\\documentclass")
                    or stripped.startswith("\\usepackage")
                    or stripped.startswith("\\geometry")
                    or stripped.startswith("\\set")
                    or stripped.startswith("\\title")
                    or stripped.startswith("\\author")
                    or stripped.startswith("\\date")
                    or stripped.startswith("\\new")
                ):
                    preamble_lines.append(line)
                else:
                    in_preamble = False
                    body_lines.append(line)
            preamble = normalize_document_preamble("\n".join(preamble_lines).strip())
            body = normalize_document_body("\n".join(body_lines)) or "% TODO: 补全文档正文"
            return f"{preamble}\n\n\\begin{{document}}\n{body}\n\\end{{document}}".strip()
        return content

    content = normalize_document_body(content)
    return (
        f"{normalize_document_preamble('')}\n\n"
        "\\begin{document}\n"
        f"{content}\n"
        "\\end{document}"
    )


def validate_tex_document(text: str) -> str | None:
    content = str(text or "")
    if not content.strip():
        return "没有可编译的 TeX 文档。"
    if "placeholder{}" in content or "\\placeholder{}" in content:
        return "文档中仍有未填写的模板占位符，请先补全后再编译。"
    return None
