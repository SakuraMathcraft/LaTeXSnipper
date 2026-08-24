from __future__ import annotations

import ast
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
FORBIDDEN_IMPORT_ROOTS = {
    "runtime": {"application", "bootstrap", "integration", "ui"},
    "backend": {"application", "bootstrap", "integration", "recognition", "ui"},
    "recognition": {"application", "bootstrap", "integration", "ui"},
}


def _absolute_import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.partition(".")[0])
    return roots


def test_lower_layers_do_not_import_application_or_ui_layers() -> None:
    violations: list[str] = []
    for package, forbidden in FORBIDDEN_IMPORT_ROOTS.items():
        for path in (SRC / package).rglob("*.py"):
            imported = _absolute_import_roots(path) & forbidden
            if imported:
                names = ", ".join(sorted(imported))
                violations.append(f"{path.relative_to(SRC)} -> {names}")
    assert not violations, "Invalid dependency direction:\n" + "\n".join(violations)
