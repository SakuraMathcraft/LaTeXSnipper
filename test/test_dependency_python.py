from __future__ import annotations

from pathlib import Path


def test_dependency_python_cleans_quoted_paths(tmp_path: Path) -> None:
    from runtime.dependency_python import clean_path_value, normalize_deps_base_dir

    python_path = str(tmp_path / "tools" / "deps" / "python311" / "python.exe")
    assert clean_path_value('"' + python_path) == python_path
    assert clean_path_value("'" + python_path + "'") == python_path
    deps_path = tmp_path / "deps" / "python"
    assert normalize_deps_base_dir(str(deps_path)) == deps_path
