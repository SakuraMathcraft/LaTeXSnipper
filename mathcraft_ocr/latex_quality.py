# coding: utf-8

from __future__ import annotations

from collections import Counter
import re


_TOKEN_RE = re.compile(r"\\[A-Za-z]+|[A-Za-z]+|\d+|[^\s]")
_BEGIN_RE = re.compile(r"\\begin\s*\{\s*([^{}]+)\s*\}")
_END_RE = re.compile(r"\\end\s*\{\s*([^{}]+)\s*\}")
_LEFT_RE = re.compile(r"\\left(?![A-Za-z])")
_RIGHT_RE = re.compile(r"\\right(?![A-Za-z])")
_DUPLICATE_EQUALS_RE = re.compile(r"(?<!\\)=\s*=")
_NOISY_REPEAT_TOKENS = {r"\quad", r"\qquad", r"\cdots", r"\ldots"}

SEVERE_LATEX_QUALITY_FLAGS = {
    "duplicate_relation",
    "repeated_token_run",
    "excessive_repeated_token",
    "unbalanced_group",
    "mismatched_environment",
}


def latex_quality_flags(text: str) -> tuple[str, ...]:
    value = str(text or "")
    flags: set[str] = set()
    if _DUPLICATE_EQUALS_RE.search(value):
        flags.add("duplicate_relation")
    if _has_repeated_token_run(value):
        flags.add("repeated_token_run")
    if _has_excessive_repeated_token(value):
        flags.add("excessive_repeated_token")
    if _group_balance(value) != 0:
        flags.add("unbalanced_group")
    if not _environments_balanced(value):
        flags.add("mismatched_environment")
    if len(_LEFT_RE.findall(value)) != len(_RIGHT_RE.findall(value)):
        flags.add("unbalanced_left_right")
    return tuple(sorted(flags))


def has_severe_latex_quality_issue(text: str) -> bool:
    return bool(set(latex_quality_flags(text)) & SEVERE_LATEX_QUALITY_FLAGS)


def _has_repeated_token_run(text: str) -> bool:
    previous = ""
    run = 0
    for token in _TOKEN_RE.findall(text):
        if token == previous:
            run += 1
        else:
            previous = token
            run = 1
        if run >= 8:
            return True
    return False


def _has_excessive_repeated_token(text: str) -> bool:
    counts = Counter(token for token in _TOKEN_RE.findall(text) if token in _NOISY_REPEAT_TOKENS)
    return any(count >= 18 for count in counts.values())


def _group_balance(text: str) -> int:
    depth = 0
    for index, char in enumerate(text):
        if char == "{" and not _is_escaped(text, index):
            depth += 1
        elif char == "}" and not _is_escaped(text, index):
            depth -= 1
    return depth


def _environments_balanced(text: str) -> bool:
    stack: list[str] = []
    for match in re.finditer(r"\\(?:begin|end)\s*\{\s*([^{}]+)\s*\}", text):
        command = match.group(0)
        env = match.group(1).strip()
        if command.startswith(r"\begin"):
            stack.append(env)
            continue
        if not stack or stack.pop() != env:
            return False
    return not stack


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    pos = index - 1
    while pos >= 0 and text[pos] == "\\":
        backslashes += 1
        pos -= 1
    return backslashes % 2 == 1
