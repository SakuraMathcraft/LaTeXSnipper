from __future__ import annotations

from pathlib import Path


def test_dependency_python_cleans_quoted_paths() -> None:
    from runtime.dependency_python import clean_path_value, normalize_deps_base_dir

    assert clean_path_value('"E:\\LaTexSnipper\\broken\\python\\python.exe') == (
        "E:\\LaTexSnipper\\broken\\python\\python.exe"
    )
    assert clean_path_value(
        "'E:\\LaTexSnipper\\tools\\deps\\python311\\python.exe'"
    ) == ("E:\\LaTexSnipper\\tools\\deps\\python311\\python.exe")
    assert normalize_deps_base_dir("E:\\LaTexSnipper\\deps\\python") == Path(
        "E:\\LaTexSnipper\\deps\\python"
    )
