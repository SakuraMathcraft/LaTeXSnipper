from __future__ import annotations

from pathlib import Path


def test_dependency_python_cleans_quoted_paths() -> None:
    from runtime.dependency_python import clean_path_value, normalize_deps_base_dir

    assert clean_path_value('"C:\\Example Project\\broken\\python\\python.exe') == (
        "C:\\Example Project\\broken\\python\\python.exe"
    )
    assert clean_path_value(
        "'C:\\Developer Envs\\mathcraft\\Scripts\\python.exe'"
    ) == ("C:\\Developer Envs\\mathcraft\\Scripts\\python.exe")
    assert normalize_deps_base_dir("C:\\Example Project\\deps\\python") == Path(
        "C:\\Example Project\\deps\\python"
    )
