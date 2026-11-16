from __future__ import annotations

import io
import json
import re
import urllib.error
from pathlib import Path
from xml.etree import ElementTree

import pytest
from latexsnipper_office import sideload
from latexsnipper_office.options import default_options, normalize_options
from latexsnipper_office.recognition import AutomationRelay, RecognitionRelayError
from latexsnipper_office.services import read_symbol_fonts
from latexsnipper_office.typography import (
    HostDefaults,
    SettingsStore,
    Typography,
    TypographyError,
    parse_points,
)

ROOT = Path(__file__).resolve().parents[3]
MACOS = ROOT / "Office_plugin/macos"
SYMBOL_FONTS = ("mathjax-tex", "mathjax-stix2")

# A preset exported by the Windows TypographySettingsStore (JavaScriptSerializer output).
WINDOWS_PRESET = (
    '{"schema":2,"followHostFontSize":true,"typography":{"typographyVersion":1,'
    '"symbolFontId":"mathjax-stix2","numberFontFamily":"Arial","cjkFontFamily":"Microsoft YaHei",'
    '"defaultMathStyle":"BoldItalic","fontSizePoints":10.5,"color":"#1f2937"}}'
)


# Typography ----------------------------------------------------------------------


def test_typography_fields_match_windows_wire_names():
    fields = Typography(number_font_family="Arial", color="#abcdef").to_fields()
    assert fields == {
        "typographyVersion": 1,
        "symbolFontId": "mathjax-tex",
        "numberFontFamily": "Arial",
        "cjkFontFamily": "PingFang SC",
        "defaultMathStyle": "Automatic",
        "fontSizePoints": 12.0,
        "color": "#ABCDEF",
    }
    assert Typography.from_fields(fields) == Typography(
        number_font_family="Arial", color="#ABCDEF"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"typographyVersion": 2},
        {"symbolFontId": "Bad Font"},
        {"defaultMathStyle": "Shiny"},
        {"fontSizePoints": 0.5},
        {"fontSizePoints": 1639},
        {"color": "red"},
        {"cjkFontFamily": "  "},
        {"cjkFontFamily": "x; url(evil)"},
        {"numberFontFamily": "a\x01b"},
    ],
)
def test_typography_rejects_invalid_snapshots(change):
    fields = {**Typography().to_fields(), **change}
    with pytest.raises(TypographyError):
        Typography.from_fields(fields)


def test_named_and_decimal_point_sizes():
    assert parse_points("小四") == 12
    assert parse_points("五号") == 10.5
    assert parse_points("10.5") == 10.5
    for invalid in ("12pt", "-1", "", True):
        with pytest.raises(TypographyError):
            parse_points(invalid)


def test_windows_preset_imports_and_reexports(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", SYMBOL_FONTS)
    imported = store.import_preset("word", WINDOWS_PRESET.encode("utf-8"))
    assert imported.follow_host_font_size is True
    assert imported.typography.default_math_style == "BoldItalic"
    assert imported.typography.font_size_points == 10.5
    exported = json.loads(store.export_preset("word"))
    assert exported == json.loads(WINDOWS_PRESET) | {
        "typography": {**json.loads(WINDOWS_PRESET)["typography"], "color": "#1F2937"}
    }
    assert store.load("word")[1] == default_options("word")
    assert store.load("powerpoint")[0] == HostDefaults()


def test_preset_with_unpackaged_symbol_font_is_rejected(tmp_path):
    store = SettingsStore(tmp_path / "settings.json", ("mathjax-tex",))
    with pytest.raises(TypographyError, match="mathjax-stix2"):
        store.import_preset("powerpoint", WINDOWS_PRESET.encode())


def test_store_persists_options_per_host_and_rebuilds_corrupt_files(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path, SYMBOL_FONTS)
    assert store.load("powerpoint")[1] == {"insertionBackend": "Png"}
    store.save(
        "powerpoint",
        HostDefaults(Typography(font_size_points=20)),
        {"insertionBackend": "Svg"},
    )
    store.save(
        "word",
        HostDefaults(),
        {"numberPlacement": "Left", "includeChapter": True, "numberSeparator": "·"},
    )
    assert store.load("powerpoint")[1] == {"insertionBackend": "Svg"}
    assert store.load("word")[1] == {
        "numberPlacement": "Left",
        "numberEnclosure": "Parentheses",
        "numberSeparator": "·",
        "includeChapter": True,
        "includeSection": False,
        "hideChapterBoundary": False,
        "hideSectionBoundary": False,
    }
    path.write_text("{not json", encoding="utf-8")
    assert store.load("powerpoint") == (HostDefaults(), {"insertionBackend": "Png"})
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == 2


def test_unknown_option_values_fall_back_to_the_windows_defaults():
    assert normalize_options(
        "word",
        {"numberEnclosure": "Angle", "numberSeparator": "|", "includeSection": "yes"},
    ) == default_options("word")
    assert normalize_options("powerpoint", {"insertionBackend": "Ole"}) == {
        "insertionBackend": "Png"
    }
    assert normalize_options("word", None) == default_options("word")


def test_symbol_font_catalog_comes_from_packaged_mathjax():
    assert read_symbol_fonts(ROOT / "src/assets/MathJax") == SYMBOL_FONTS


# Sideloading ---------------------------------------------------------------------


def test_manifest_renders_and_is_valid_xml():
    rendered = sideload.render_manifest(
        (MACOS / "manifest.xml").read_text(encoding="utf-8"),
        base_url="https://localhost:28766",
        product_version="3.3.0",
        icons=MACOS / "web/icons",
    )
    root = ElementTree.fromstring(rendered)
    namespace = {"o": "http://schemas.microsoft.com/office/appforoffice/1.1"}
    assert root.find("o:Version", namespace).text == "3.3.0.0"
    assert "{{" not in rendered
    assert re.search(r'/addin/icons/delete-32\.png\?v=[0-9a-f]{12}"', rendered)


def test_changed_icon_gets_a_new_url(tmp_path):
    template = '<x v="{{VERSION}}" i="{{BASE_URL}}/addin/icons/a-16.png"/>'
    icon = tmp_path / "a-16.png"
    render = lambda: sideload.render_manifest(  # noqa: E731
        template, base_url="https://localhost:1", product_version="1", icons=tmp_path
    )
    icon.write_bytes(b"old")
    before = render()
    icon.write_bytes(b"new")
    assert render() != before


def test_manifest_resources_exist_and_commands_are_registered():
    template = (MACOS / "manifest.xml").read_text(encoding="utf-8")
    for icon in re.findall(r"\{\{BASE_URL\}\}/addin/(icons/[\w.-]+\.png)", template):
        assert (MACOS / "web" / icon).is_file(), icon
    for page in re.findall(r"\{\{BASE_URL\}\}/addin/([\w-]+\.html)", template):
        assert (MACOS / "web" / page).is_file(), page
    controller = (MACOS / "web/app/controller.mjs").read_text(encoding="utf-8")
    for function in set(re.findall(r"<FunctionName>(\w+)</FunctionName>", template)):
        assert re.search(rf"\b{function}: \(\) =>", controller), function


@pytest.mark.parametrize("version", ["3", "3.3.0", "1.2.3.4"])
def test_manifest_version_has_four_parts(version):
    assert len(sideload.manifest_version(version).split(".")) == 4


@pytest.mark.parametrize("version", ["", "3.x", "1.2.3.4.5", "v3.3.0"])
def test_manifest_version_rejects_invalid_values(version):
    with pytest.raises(ValueError):
        sideload.manifest_version(version)


def test_install_and_remove_touch_only_this_add_in(tmp_path):
    other = sideload.wef_directory("com.microsoft.Word", tmp_path) / "someone-else.xml"
    other.parent.mkdir(parents=True)
    other.write_text("<OfficeApp/>", encoding="utf-8")
    written = sideload.install_manifest("<OfficeApp/>", home=tmp_path)
    assert len(written) == 2
    assert sideload.installed_hosts(tmp_path) == ["word", "powerpoint"]
    assert sorted(path.name for path in other.parent.iterdir()) == [
        sideload.MANIFEST_FILENAME,
        "someone-else.xml",
    ]
    sideload.remove_manifest(tmp_path)
    assert sideload.installed_hosts(tmp_path) == []
    assert other.is_file()


# Recognition relay ----------------------------------------------------------------


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def connection_file(tmp_path, base_url="http://127.0.0.1:28765"):
    path = tmp_path / "automation-api.json"
    path.write_text(
        json.dumps({"base_url": base_url, "token": "secret-token"}), encoding="utf-8"
    )
    return path


def test_relay_authenticates_and_forwards_next_result(tmp_path):
    seen = []

    def opener(request, timeout):
        seen.append(request)
        return FakeResponse(b'{"job":{"id":"j1","state":"awaiting_result"}}')

    relay = AutomationRelay(connection_file(tmp_path), opener=opener)
    assert relay.next_result(90)["job"]["id"] == "j1"
    request = seen[0]
    assert request.full_url == "http://127.0.0.1:28765/api/v1/recognition/jobs"
    assert request.get_header("Authorization") == "Bearer secret-token"
    assert json.loads(request.data) == {"input": {"type": "next_result"}, "timeout": 90}


def test_relay_maps_job_errors_to_user_messages(tmp_path):
    payload = b'{"job":{"id":"j1","state":"failed","error":{"code":"model_unavailable","message":"x"}}}'
    relay = AutomationRelay(
        connection_file(tmp_path), opener=lambda request, timeout: FakeResponse(payload)
    )
    assert "MathCraft" in relay.job("j1")["job"]["error"]["message"]


def test_relay_reports_missing_desktop_and_http_errors(tmp_path):
    relay = AutomationRelay(tmp_path / "missing.json", opener=lambda *a, **k: None)
    with pytest.raises(RecognitionRelayError) as missing:
        relay.config()
    assert missing.value.code == "desktop_unavailable"

    def busy(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            409,
            "busy",
            {},
            io.BytesIO(b'{"error":{"code":"next_result_busy"}}'),
        )

    relay = AutomationRelay(connection_file(tmp_path), opener=busy)
    with pytest.raises(RecognitionRelayError) as error:
        relay.next_result(10)
    assert (error.value.status, error.value.code) == (409, "next_result_busy")


def test_relay_cancels_its_own_stale_wait_and_retries_once(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "latexsnipper_office.recognition.time.sleep", lambda seconds: None
    )
    calls = []
    answers = [
        b'{"job":{"id":"old"}}',
        "busy",
        b'{"job":{"id":"old","state":"canceled"}}',
        b'{"job":{"id":"new"}}',
    ]

    def opener(request, timeout):
        calls.append((request.get_method(), request.full_url.rsplit("/", 1)[-1]))
        answer = answers.pop(0)
        if answer == "busy":
            raise urllib.error.HTTPError(
                request.full_url,
                409,
                "busy",
                {},
                io.BytesIO(b'{"error":{"code":"next_result_busy"}}'),
            )
        return FakeResponse(answer)

    relay = AutomationRelay(connection_file(tmp_path), opener=opener)
    assert relay.next_result(10)["job"]["id"] == "old"
    assert relay.next_result(10)["job"]["id"] == "new"
    assert calls == [
        ("POST", "jobs"),
        ("POST", "jobs"),
        ("DELETE", "old"),
        ("POST", "jobs"),
    ]


@pytest.mark.parametrize(
    "base_url", ["http://192.168.1.2:28765", "file:///etc/passwd", "http://example.com"]
)
def test_relay_only_talks_to_loopback(tmp_path, base_url):
    relay = AutomationRelay(
        connection_file(tmp_path, base_url), opener=lambda *a, **k: None
    )
    with pytest.raises(RecognitionRelayError) as error:
        relay.config()
    assert error.value.code == "connection_invalid"


def test_relay_job_ids_are_path_escaped(tmp_path):
    seen = []
    relay = AutomationRelay(
        connection_file(tmp_path),
        opener=lambda request, timeout: seen.append(request) or FakeResponse(b"{}"),
    )
    relay.cancel("a/../b")
    assert seen[0].full_url.endswith("/api/v1/recognition/jobs/a%2F..%2Fb")
    assert seen[0].get_method() == "DELETE"
