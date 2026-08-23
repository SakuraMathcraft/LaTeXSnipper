from __future__ import annotations

from pathlib import Path


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


def test_cross_platform_packaging_docs_do_not_reference_missing_scripts() -> None:
    readme = (ROOT / "readme.md").read_text(encoding="utf-8")

    referenced_paths = (
        "scripts/build_deb.sh",
        "scripts/build_macos.sh",
        "LaTeXSnipper-linux.spec",
        "LaTeXSnipper-linux-offline.spec",
        "LaTeXSnipper-macos.spec",
        "packaging/debian",
    )
    for rel_path in referenced_paths:
        if rel_path in readme:
            assert (ROOT / rel_path).exists()


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
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in BOM_CHECK_EXTENSIONS:
                continue
            if path.name.endswith(".user.props"):
                continue
            if ignored_parts.intersection(path.parts):
                continue
            if path.read_bytes().startswith(b"\xef\xbb\xbf"):
                offenders.append(path.relative_to(ROOT).as_posix())

    assert offenders == []
