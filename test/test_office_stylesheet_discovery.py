from __future__ import annotations

import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from exporting import formula_converters


@pytest.fixture
def registry(monkeypatch):
    entries = {}
    registry = SimpleNamespace(
        HKEY_CURRENT_USER="user",
        HKEY_LOCAL_MACHINE="machine",
        KEY_WOW64_64KEY=0x100,
        KEY_WOW64_32KEY=0x200,
        KEY_READ=1,
        REG_SZ=1,
        REG_EXPAND_SZ=2,
    )

    def open_key(hive, key_path, reserved, access):
        entry = (hive, access & ~registry.KEY_READ)
        if (
            key_path
            != r"Software\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE"
            or entry not in entries
        ):
            raise FileNotFoundError(key_path)
        return nullcontext(entry)

    registry.OpenKey = open_key
    registry.QueryValueEx = lambda key, name: entries[key]
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(formula_converters, "sys", SimpleNamespace(platform="win32"))
    return entries, registry


@pytest.fixture
def office(tmp_path):
    directory = tmp_path / "自定义 Office 安装" / "root" / "Office16"
    directory.mkdir(parents=True)
    (directory / "WINWORD.EXE").touch()
    stylesheet = directory / "MML2OMML.XSL"
    stylesheet.touch()
    return directory


@pytest.mark.parametrize("hive", ["user", "machine"])
@pytest.mark.parametrize("view", [0x100, 0x200])
def test_finds_stylesheet_beside_registered_word(registry, office, hive, view):
    entries, api = registry
    entries[hive, view] = (f'"{office / "WINWORD.EXE"}"', api.REG_SZ)

    assert formula_converters._find_mml2omml_xsl() == office / "MML2OMML.XSL"


def test_expands_registered_word_environment_variables(registry, office):
    entries, api = registry
    entries["machine", 0x100] = (r"%OFFICE_ROOT%\WINWORD.EXE", api.REG_EXPAND_SZ)
    api.ExpandEnvironmentStrings = lambda value: value.replace(
        "%OFFICE_ROOT%", str(office)
    )

    assert formula_converters._find_mml2omml_xsl() == office / "MML2OMML.XSL"


@pytest.mark.parametrize("failure", ["missing_executable", "missing_stylesheet"])
def test_checks_other_registrations_after_unusable_installation(
    registry, office, tmp_path, failure
):
    entries, api = registry
    stale_word = tmp_path / "incomplete-office" / "WINWORD.EXE"
    stale_word.parent.mkdir()
    if failure == "missing_stylesheet":
        stale_word.touch()
    entries["user", 0x100] = (str(stale_word), api.REG_SZ)
    entries["machine", 0x200] = (str(office / "WINWORD.EXE"), api.REG_SZ)

    assert formula_converters._find_mml2omml_xsl() == office / "MML2OMML.XSL"


def test_unregistered_word_cannot_supply_stylesheet(registry):
    assert formula_converters._find_mml2omml_xsl() is None


def test_relative_registered_word_path_is_rejected(registry, office, monkeypatch):
    entries, api = registry
    monkeypatch.chdir(office)
    entries["user", 0x100] = ("WINWORD.EXE", api.REG_SZ)

    assert formula_converters._find_mml2omml_xsl() is None


def test_omml_export_reports_missing_stylesheet(monkeypatch):
    monkeypatch.setattr(formula_converters, "_find_mml2omml_xsl", lambda: None)
    formula_converters._cached_mml2omml_transform.cache_clear()

    with pytest.raises(RuntimeError, match="MML2OMML.XSL was not found"):
        formula_converters._cached_mml2omml_transform()
