# coding: utf-8

from __future__ import annotations


RELATION_COMMANDS = (
    r"\leqslant",
    r"\geqslant",
    r"\leq",
    r"\geq",
    r"\approx",
    r"\equiv",
    r"\sim",
)
RELATION_SYMBOLS = ("=", "<", ">")


def align_latex_relation_lines(lines: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    cleaned = [line.strip() for line in lines if line and line.strip()]
    if len(cleaned) <= 1:
        return tuple(cleaned)

    aligned: list[str] = []
    saw_relation = False
    for index, line in enumerate(cleaned):
        relation = find_alignment_relation(line)
        if relation is None:
            if index > 0 and saw_relation:
                aligned.append(r"&\quad " + line)
            else:
                aligned.append(line)
            continue

        left, operator, right = relation
        saw_relation = True
        if left:
            aligned.append(f"{left} &{operator} {right}".rstrip())
        else:
            aligned.append(f"&{operator} {right}".rstrip())
    return tuple(aligned)


def find_alignment_relation(text: str) -> tuple[str, str, str] | None:
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            command = _read_command(text, index)
            if depth == 0 and command in RELATION_COMMANDS:
                return _split_relation(text, index, command)
            index += len(command) if command else 1
            continue
        if char == "{" and not _is_escaped(text, index):
            depth += 1
            index += 1
            continue
        if char == "}" and not _is_escaped(text, index):
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth == 0 and char in RELATION_SYMBOLS and not _is_escaped(text, index):
            if _is_duplicate_relation_neighbor(text, index, char):
                index += 1
                continue
            return _split_relation(text, index, char)
        index += 1
    return None


def _split_relation(text: str, index: int, operator: str) -> tuple[str, str, str]:
    left = text[:index].strip()
    right = text[index + len(operator) :].strip()
    return left, operator, right


def _read_command(text: str, index: int) -> str:
    if index >= len(text) or text[index] != "\\":
        return ""
    end = index + 1
    while end < len(text) and text[end].isalpha():
        end += 1
    return text[index:end]


def _is_duplicate_relation_neighbor(text: str, index: int, char: str) -> bool:
    if char != "=":
        return False
    left = text[:index].rstrip()
    right = text[index + 1 :].lstrip()
    return left.endswith("=") or right.startswith("=")


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    pos = index - 1
    while pos >= 0 and text[pos] == "\\":
        backslashes += 1
        pos -= 1
    return backslashes % 2 == 1
