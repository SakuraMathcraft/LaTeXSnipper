from __future__ import annotations

import ast
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOM_CHECK_ROOTS = (
    ".github",
    "benchmarks",
    "docs",
    "Inno",
    "mathcraft_ocr",
    "office_plugin",
    "packaging",
    "scripts",
    "src",
    "test",
    "tools/mathjax",
    "user_manual",
)
BOM_CHECK_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".cs",
    ".csproj",
    ".css",
    ".html",
    ".iss",
    ".isl",
    ".js",
    ".json",
    ".md",
    ".props",
    ".ps1",
    ".py",
    ".rc",
    ".sh",
    ".targets",
    ".txt",
    ".typ",
    ".xml",
    ".yaml",
    ".yml",
}


def test_debian_control_template_is_dpkg_safe() -> None:
    control_bytes = (ROOT / "packaging" / "debian" / "DEBIAN" / "control").read_bytes()

    assert not control_bytes.startswith(b"\xef\xbb\xbf")
    assert control_bytes.startswith(b"Package: latexsnipper\n")


def test_text_sources_are_utf8_without_bom() -> None:
    offenders: list[str] = []
    ignored_parts = {"bin", "obj", "node_modules"}
    for root_name in BOM_CHECK_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [
                name for name in subdirectories if name not in ignored_parts
            ]
            for name in files:
                path = Path(directory) / name
                if path.suffix.lower() not in BOM_CHECK_EXTENSIONS or name.endswith(
                    ".user.props"
                ):
                    continue
                data = path.read_bytes()
                try:
                    data.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    offenders.append(path.relative_to(ROOT).as_posix())
                else:
                    if data.startswith(b"\xef\xbb\xbf"):
                        offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []


def test_text_files_and_subprocess_pipes_declare_utf8() -> None:
    offenders = []
    for root in ("src", "mathcraft_ocr", "scripts", "tools/mathjax", "benchmarks"):
        for path in (ROOT / root).rglob("*.py"):
            if "vendor" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for call in ast.walk(tree):
                if not isinstance(call, ast.Call):
                    continue
                function = call.func
                name = (
                    function.attr
                    if isinstance(function, ast.Attribute)
                    else function.id
                    if isinstance(function, ast.Name)
                    else ""
                )
                keywords = {item.arg: item.value for item in call.keywords}
                text_file = name in {"read_text", "write_text"}
                if name == "open" and isinstance(function, ast.Name):
                    mode = keywords.get(
                        "mode",
                        call.args[1] if len(call.args) > 1 else ast.Constant("r"),
                    )
                    text_file = (
                        isinstance(mode, ast.Constant)
                        and isinstance(mode.value, str)
                        and "b" not in mode.value
                    )
                text_pipe = name in {"run", "Popen", "check_output"} and any(
                    isinstance(keywords.get(key), ast.Constant) and keywords[key].value
                    for key in ("text", "universal_newlines")
                )
                if not (text_file or text_pipe):
                    continue
                encoding = keywords.get("encoding")
                if not isinstance(encoding, ast.Constant) or encoding.value not in {
                    "utf-8",
                    "utf-8-sig",
                }:
                    offenders.append(f"{path.relative_to(ROOT)}:{call.lineno}")
    assert offenders == []


if __name__ == "__main__":
    test_text_sources_are_utf8_without_bom()
    test_text_files_and_subprocess_pipes_declare_utf8()
