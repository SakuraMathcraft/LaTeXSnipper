from __future__ import annotations

from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]
BOM_CHECK_ROOTS = (
    ".github",
    "docs",
    "Inno",
    "office_plugin",
    "packaging",
    "scripts",
    "src",
    "test",
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


def test_text_sources_do_not_use_utf8_bom() -> None:
    offenders: list[str] = []
    ignored_parts = {"bin", "obj", "node_modules"}
    for root_name in BOM_CHECK_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [name for name in subdirectories if name not in ignored_parts]
            for name in files:
                path = Path(directory) / name
                if path.suffix.lower() not in BOM_CHECK_EXTENSIONS or name.endswith('.user.props'):
                    continue
                with path.open('rb') as stream:
                    if stream.read(3) == b"\xef\xbb\xbf":
                        offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []
