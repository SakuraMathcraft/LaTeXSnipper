# -*- coding: utf-8 -*-
"""Convert normalized MathCraft Markdown documents to compilable LaTeX."""

from __future__ import annotations

import re


_HEADING_RE = re.compile(r"^(#{1,5})\s+(.+?)\s*$")
_LIST_RE = re.compile(r"^[-*]\s+(.+?)\s*$")
_HTML_COMMENT_RE = re.compile(r"^<!--\s*(.*?)\s*-->$")


def markdown_to_latex_document(markdown: str) -> str:
    """Convert a normalized MathCraft Markdown document into a full LaTeX document."""
    text = (markdown or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    if "\\documentclass" in text and "\\begin{document}" in text:
        return text if text.endswith("\n") else text + "\n"

    body, title = _markdown_to_latex_body(text)
    return _wrap_latex_document(body, title=title)


def _markdown_to_latex_body(text: str) -> tuple[str, str]:
    lines = text.split("\n")
    chunks: list[str] = []
    paragraph: list[str] = []
    list_open = False
    title = ""
    i = 0

    def flush_paragraph() -> None:
        if not paragraph:
            return
        joined = " ".join(part.strip() for part in paragraph if part.strip())
        paragraph.clear()
        if joined:
            chunks.append(_convert_inline_markdown(joined))

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            chunks.append("\\end{itemize}")
            list_open = False

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        if not line:
            flush_paragraph()
            close_list()
            i += 1
            continue

        if line.startswith("$$"):
            flush_paragraph()
            close_list()
            math_lines: list[str] = []
            first = line[2:].strip()
            if first.endswith("$$") and first != "$$":
                math_lines.append(first[:-2].strip())
                i += 1
            else:
                if first:
                    math_lines.append(first)
                i += 1
                while i < len(lines):
                    candidate = lines[i].strip()
                    if _HTML_COMMENT_RE.match(candidate):
                        break
                    if candidate.startswith("$$"):
                        tail = candidate[2:].strip()
                        if tail.startswith("$") and not tail.startswith("$$"):
                            tail = tail[1:].strip()
                        if tail.endswith("$") and not tail.endswith("$$"):
                            tail = tail[:-1].strip()
                        if tail:
                            math_lines.append(tail)
                        i += 1
                        break
                    if candidate.endswith("$$"):
                        tail = candidate[:-2].strip()
                        if tail:
                            math_lines.append(tail)
                        i += 1
                        break
                    math_lines.append(lines[i].rstrip())
                    i += 1
            if any(line.strip() for line in math_lines):
                chunks.append(_render_display_math("\n".join(math_lines)))
            continue

        comment = _HTML_COMMENT_RE.match(line)
        if comment:
            flush_paragraph()
            close_list()
            content = comment.group(1).strip()
            if content:
                chunks.append(f"% {content}")
            i += 1
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            heading_text = _strip_auto_numbered_heading_prefix(heading.group(2).strip())
            if level == 1 and not title:
                title = heading_text
            else:
                chunks.append(_render_heading(level, heading_text))
            i += 1
            continue

        item = _LIST_RE.match(line)
        if item:
            flush_paragraph()
            if not list_open:
                chunks.append("\\begin{itemize}")
                list_open = True
            chunks.append(f"\\item {_convert_inline_markdown(item.group(1).strip())}")
            i += 1
            continue

        if line.startswith("[IMAGE_PLACEHOLDER:") and line.endswith("]"):
            flush_paragraph()
            close_list()
            chunks.append(f"% {_escape_latex_text(line)}")
            i += 1
            continue

        close_list()
        paragraph.append(line)
        i += 1

    flush_paragraph()
    close_list()
    return "\n\n".join(chunk for chunk in chunks if chunk.strip()).strip(), title


def _render_heading(level: int, text: str) -> str:
    escaped = _convert_inline_markdown(text)
    command = {
        2: "section",
        3: "subsection",
        4: "subsubsection",
    }.get(level, "paragraph")
    if command == "paragraph":
        return f"\\paragraph{{{escaped}}}"
    return f"\\{command}{{{escaped}}}"


def _strip_auto_numbered_heading_prefix(text: str) -> str:
    line = (text or "").strip()
    patterns = [
        r"^\d+(?:\.\d+)*\.?\s+(.+?)\s*$",
        r"^Chapter\s+\d+\.?\s+(.+?)\s*$",
        r"^第\s*\d+\s*章\s*(.+?)\s*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, line, flags=re.IGNORECASE)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return line


def _render_display_math(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return "\\[\n\\]"
    if body.startswith("$") and not body.startswith("$$"):
        body = body[1:].strip()
    if body.endswith("$") and not body.endswith("$$"):
        body = body[:-1].strip()
    body = _repair_display_math_for_tex(body)
    return f"\\[\n{body}\n\\]"


def _repair_display_math_for_tex(text: str) -> str:
    """Apply minimal syntax repairs so OCR-truncated display math can compile."""
    body = _strip_orphan_trailing_backslash((text or "").strip())
    if not body:
        return body

    body = _remove_extra_closing_braces(body)
    body = _repair_incomplete_two_arg_commands(body)
    if _needs_display_math_tail_repair(body):
        body = _normalize_dynamic_delimiters(body)
    body = _append_display_math_tail_repairs(body)
    return body.strip()


def _strip_orphan_trailing_backslash(text: str) -> str:
    body = (text or "").rstrip()
    body = re.sub(r"(?:\\\\\s*)+$", "", body).rstrip()
    while body.endswith("\\") and not body.endswith("\\\\"):
        body = body[:-1].rstrip()
    return body


def _remove_extra_closing_braces(text: str) -> str:
    depth = 0
    result: list[str] = []
    for idx, ch in enumerate(text):
        if ch == "{" and not _is_escaped_at(text, idx):
            depth += 1
            result.append(ch)
            continue
        if ch == "}" and not _is_escaped_at(text, idx):
            if depth <= 0:
                continue
            depth -= 1
            result.append(ch)
            continue
        result.append(ch)
    return "".join(result)


def _repair_incomplete_two_arg_commands(text: str) -> str:
    command_re = re.compile(r"\\(?:dfrac|tfrac|frac|binom)\b")
    edits: list[tuple[int, str]] = []
    for match in command_re.finditer(text):
        pos = _skip_spaces(text, match.end())
        first_end = _braced_group_end(text, pos)
        if first_end < 0:
            edits.append((match.end(), " {} {}"))
            continue
        second_pos = _skip_spaces(text, first_end)
        if _braced_group_end(text, second_pos) < 0:
            edits.append((first_end, " {}"))
    if not edits:
        return text
    repaired = text
    for pos, insertion in reversed(edits):
        repaired = repaired[:pos] + insertion + repaired[pos:]
    return repaired


def _skip_spaces(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _braced_group_end(text: str, pos: int) -> int:
    if pos >= len(text) or text[pos] != "{":
        return -1
    depth = 0
    for idx in range(pos, len(text)):
        ch = text[idx]
        if _is_escaped_at(text, idx):
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return idx + 1
    return -1


def _append_display_math_tail_repairs(text: str) -> str:
    env_stack = _unclosed_math_environment_stack(text)
    brace_positions = _unmatched_open_brace_positions(text)
    left_positions = _unmatched_left_positions(text)
    if not env_stack and not brace_positions and not left_positions:
        return text

    suffix: list[str] = []
    for env, env_pos in reversed(env_stack):
        while left_positions and left_positions[-1] > env_pos:
            suffix.append(" \\right.")
            left_positions.pop()
        while brace_positions and brace_positions[-1] > env_pos:
            suffix.append("}")
            brace_positions.pop()
        suffix.append(f"\n\\end{{{env}}}")

    while left_positions:
        suffix.append(" \\right.")
        left_positions.pop()
    while brace_positions:
        suffix.append("}")
        brace_positions.pop()
    return text.rstrip() + "".join(suffix)


def _needs_display_math_tail_repair(text: str) -> bool:
    return bool(
        _unclosed_math_environment_stack(text)
        or _unmatched_open_brace_positions(text)
        or _unmatched_left_positions(text)
    )


def _normalize_dynamic_delimiters(text: str) -> str:
    body = re.sub(r"\\left\s*\.", "", text)
    body = re.sub(r"\\right\s*\.", "", body)
    body = re.sub(r"\\left\s*", "", body)
    body = re.sub(r"\\right\s*", "", body)
    return body


def _unclosed_math_environment_stack(text: str) -> list[tuple[str, int]]:
    stack: list[tuple[str, int]] = []
    for match in re.finditer(r"\\(begin|end)\s*\{\s*([A-Za-z*]+)\s*\}", text):
        action, env = match.groups()
        if action == "begin":
            stack.append((env, match.start()))
            continue
        for idx in range(len(stack) - 1, -1, -1):
            if stack[idx][0] == env:
                del stack[idx:]
                break
    return stack


def _unmatched_open_brace_positions(text: str) -> list[int]:
    stack: list[int] = []
    for idx, ch in enumerate(text):
        if _is_escaped_at(text, idx):
            continue
        if ch == "{":
            stack.append(idx)
        elif ch == "}" and stack:
            stack.pop()
    return stack


def _unmatched_left_positions(text: str) -> list[int]:
    stack: list[int] = []
    for match in re.finditer(r"(?<!\\)\\(left|right)\b", text):
        if match.group(1) == "left":
            stack.append(match.start())
        elif stack:
            stack.pop()
    return stack


def _is_escaped_at(text: str, idx: int) -> bool:
    slash_count = 0
    pos = idx - 1
    while pos >= 0 and text[pos] == "\\":
        slash_count += 1
        pos -= 1
    return slash_count % 2 == 1


def _wrap_latex_document(body: str, title: str = "") -> str:
    preamble = [
        "\\documentclass[11pt,a4paper]{ctexart}",
        "\\usepackage[margin=1in]{geometry}",
        "\\usepackage{amsmath,amssymb,amsthm,mathtools,bm}",
        "\\usepackage{graphicx}",
        "\\usepackage{booktabs,longtable,array,multirow}",
        "\\usepackage{enumitem}",
        "\\usepackage{hyperref}",
        "\\hypersetup{hidelinks}",
        "\\setlength{\\parindent}{2em}",
        "\\setlength{\\parskip}{0.35em}",
    ]
    if title:
        preamble.append(f"\\title{{{_convert_inline_markdown(title)}}}")
        preamble.append("\\date{}")
    preamble.append("\\begin{document}")
    if title:
        preamble.append("\\maketitle")
    return "\n".join(preamble) + "\n\n" + body.rstrip() + "\n\n\\end{document}\n"


def _convert_inline_markdown(text: str) -> str:
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        start = _find_unescaped_dollar(text, pos)
        if start < 0:
            parts.append(_escape_markdown_text(text[pos:]))
            break
        end = _find_unescaped_dollar(text, start + 1)
        if end < 0:
            parts.append(_escape_markdown_text(text[pos:]))
            break
        parts.append(_escape_markdown_text(text[pos:start]))
        math_body = text[start + 1 : end].strip()
        parts.append(f"${math_body}$")
        pos = end + 1
    return "".join(parts).strip()


def _find_unescaped_dollar(text: str, start: int) -> int:
    pos = start
    while True:
        idx = text.find("$", pos)
        if idx < 0:
            return -1
        if idx == 0 or text[idx - 1] != "\\":
            return idx
        pos = idx + 1


def _escape_markdown_text(text: str) -> str:
    result: list[str] = []
    pos = 0
    while pos < len(text):
        start = text.find("**", pos)
        if start < 0:
            result.append(_escape_latex_text(text[pos:]))
            break
        end = text.find("**", start + 2)
        if end < 0:
            result.append(_escape_latex_text(text[pos:]))
            break
        result.append(_escape_latex_text(text[pos:start]))
        bold_text = text[start + 2 : end].strip()
        result.append(f"\\textbf{{{_escape_latex_text(bold_text)}}}")
        pos = end + 2
    return "".join(result)


def _escape_latex_text(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)
