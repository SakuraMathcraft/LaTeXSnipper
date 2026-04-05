from __future__ import annotations

import re


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
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    return value.rstrip()


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
        if stripped.startswith(r"\[") or stripped.startswith("$$") or stripped.startswith(r"\begin{"):
            in_math_block = True
            normalized.append(line)
            continue
        if stripped.startswith(r"\]") or stripped.endswith("$$") or stripped.startswith(r"\end{"):
            normalized.append(line)
            in_math_block = False
            continue
        if in_math_block or not looks_like_naked_formula_line(stripped):
            normalized.append(line)
            continue
        normalized.extend([r"\[", stripped, r"\]"])
    return "\n".join(normalized).strip()


def wrap_tex_document(text: str) -> str:
    content = sanitize_tex_templates(str(text or "")).strip()
    if not content:
        return ""
    if "\\documentclass" in content and "\\begin{document}" in content and "\\end{document}" in content:
        begin_idx = content.find("\\begin{document}")
        end_idx = content.rfind("\\end{document}")
        if begin_idx >= 0 and end_idx > begin_idx:
            begin_token = "\\begin{document}"
            preamble = content[: begin_idx + len(begin_token)].rstrip()
            body = content[begin_idx + len(begin_token): end_idx].strip()
            normalized_body = normalize_document_body(body) or "% TODO: 补全文档正文"
            suffix = content[end_idx:].strip()
            return f"{preamble}\n{normalized_body}\n{suffix}".strip()
        return content

    if "\\documentclass" in content:
        if "\\begin{document}" in content and "\\end{document}" not in content:
            return content + "\n\\end{document}"
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
            preamble = "\n".join(preamble_lines).strip()
            body = normalize_document_body("\n".join(body_lines)) or "% TODO: 补全文档正文"
            return f"{preamble}\n\n\\begin{{document}}\n{body}\n\\end{{document}}".strip()
        return content

    content = normalize_document_body(content)
    return (
        "\\documentclass[UTF8]{ctexart}\n"
        "\\usepackage{amsmath,amssymb,amsthm,mathtools,bm}\n"
        "\\usepackage{geometry}\n"
        "\\usepackage{graphicx}\n"
        "\\usepackage{booktabs}\n"
        "\\usepackage{array}\n"
        "\\usepackage{multirow}\n"
        "\\geometry{a4paper,margin=2.2cm}\n\n"
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
