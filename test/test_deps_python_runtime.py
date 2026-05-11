from bootstrap import deps_python_runtime


def test_find_local_python311_installer_walks_from_module_to_project_root(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    module_file = project_root / "src" / "bootstrap" / "deps_bootstrap.py"
    deps_dir = project_root / "src" / "deps"
    installer = project_root / "python-3.11.0-amd64.exe"
    other_cwd = tmp_path / "other"

    module_file.parent.mkdir(parents=True)
    deps_dir.mkdir(parents=True)
    other_cwd.mkdir()
    (project_root / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    installer.write_bytes(b"installer")

    monkeypatch.setattr(deps_python_runtime.os, "name", "nt")
    monkeypatch.chdir(other_cwd)

    found = deps_python_runtime.find_local_python311_installer(deps_dir, str(module_file))

    assert found == installer


def test_find_local_python311_installer_checks_pyinstaller_internal_dir(tmp_path, monkeypatch):
    deps_dir = tmp_path / "deps"
    internal_dir = tmp_path / "app" / "_internal"
    installer = internal_dir / "python-3.11.0-amd64.exe"

    deps_dir.mkdir()
    internal_dir.mkdir(parents=True)
    installer.write_bytes(b"installer")

    monkeypatch.setattr(deps_python_runtime.os, "name", "nt")
    monkeypatch.setattr(deps_python_runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(deps_python_runtime.sys, "_MEIPASS", str(internal_dir), raising=False)

    found = deps_python_runtime.find_local_python311_installer(deps_dir, __file__)

    assert found == installer
