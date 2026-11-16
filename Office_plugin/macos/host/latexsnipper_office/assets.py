"""Locate the files served to Office: add-in pages, shared editor, MathJax.

Source checkouts read the Windows plugin's shared editor and renderer files in
place, so both platforms always run one implementation. The packaged add-in
carries its own copies, including the MathJax ``office`` resource profile
that the Windows installer also ships (see ``Office_plugin/macos/build.py``);
nothing is read from the LaTeXSnipper desktop installation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from latexsnipper_office.paths import resources_root

PACKAGED_DIRECTORY = "office_addin"
PACKAGED_MATHJAX = "MathJax"
TYPOGRAPHY_ADAPTER = "MathJaxTypographyAdapter.js"
MANIFEST_TEMPLATE = "manifest.xml"


@dataclass(frozen=True)
class OfficeAddinAssets:
    web: Path
    shared_editor: Path
    typography_adapter: Path
    manifest_template: Path
    mathjax: Path
    support: Path

    def validate(self) -> None:
        required = (
            self.web / "taskpane.html",
            self.shared_editor / "editor.js",
            self.typography_adapter,
            self.manifest_template,
            self.mathjax / "startup.js",
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("Office 加载项资源缺失：" + ", ".join(missing))


def packaged_assets(root: Path, mathjax: Path) -> OfficeAddinAssets:
    return OfficeAddinAssets(
        web=root / "web",
        shared_editor=root / "shared",
        typography_adapter=root / TYPOGRAPHY_ADAPTER,
        manifest_template=root / MANIFEST_TEMPLATE,
        mathjax=mathjax,
        support=root / "support",
    )


def source_assets(repository: Path, mathjax: Path) -> OfficeAddinAssets:
    plugin = repository / "Office_plugin"
    return OfficeAddinAssets(
        web=plugin / "macos/web",
        shared_editor=plugin / "shared/EditorAssets",
        typography_adapter=plugin / "shared/mathjax" / TYPOGRAPHY_ADAPTER,
        manifest_template=plugin / "macos" / MANIFEST_TEMPLATE,
        mathjax=mathjax,
        # Help-page images are owned by the Windows plugin; both help pages show them.
        support=plugin / "windows/hosts/WordAddIn/EditorAssets/support",
    )


def resolve_assets() -> OfficeAddinAssets:
    root = resources_root()
    packaged = root / PACKAGED_DIRECTORY
    if packaged.is_dir():
        return packaged_assets(packaged, packaged / PACKAGED_MATHJAX)
    return source_assets(root, root / "src/assets/MathJax")
