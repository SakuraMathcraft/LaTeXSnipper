"""Build-cache identities follow the files actually used by each component."""

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_desktop_release as build  # noqa: E402


def test_isolated_build_python_uses_utf8_for_unicode_output(tmp_path, monkeypatch):
    import build_inference_component as inference

    monkeypatch.setattr(
        inference, "python_executable", lambda _root: Path(sys.executable)
    )
    text = "中文 − 𝛼 🙂"
    result = inference.run_python(
        tmp_path,
        "import sys; assert sys.flags.utf8_mode == 1; print(sys.argv[1]); sys.stderr.write(sys.argv[1])",
        [text],
    )
    assert result == text + "\n"


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    locks = tmp_path / "packaging/runtime"
    locks.mkdir(parents=True)
    for name in ("sources.lock.json", "resources.lock.json"):
        shutil.copy2(ROOT / "packaging/runtime" / name, locks / name)
    monkeypatch.setattr(build, "ROOT", tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    ("target", "path", "affected"),
    [
        ("windows-x86_64", "scripts/normalize_windows_crt.ps1", {"application"}),
        ("linux-x86_64", "scripts/linux_hotkey_packaging.py", {"application"}),
        ("linux-x86_64", "packaging/debian/DEBIAN/control", {"application"}),
        ("linux-x86_64", "requirements-linux.txt", {"application"}),
        ("macos-arm64", "requirements-macos.txt", {"application"}),
        ("windows-x86_64", "mathcraft_ocr/vendor/LICENSE.onnx", {"application"}),
        ("windows-x86_64", "scripts/payload_pruning.py", {"application", "inference"}),
        (
            "macos-arm64",
            "packaging/macos/entitlements.plist",
            {"application", "inference"},
        ),
        (
            "windows-x86_64",
            "src/runtime/inference_probe.py",
            {"application", "inference"},
        ),
    ],
)
def test_build_input_changes_invalidate_the_owning_components(
    inputs, target, path, affected
):
    source = inputs / path
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("before", encoding="utf-8")
    before = build.build_inputs(target)
    source.write_text("after", encoding="utf-8")
    after = build.build_inputs(target)
    assert {name for name in before if before[name] != after[name]} == affected


def test_unrelated_platform_requirements_preserve_cached_components(inputs):
    before = build.build_inputs("windows-x86_64")
    (inputs / "requirements-macos.txt").write_text("changed", encoding="utf-8")
    assert build.build_inputs("windows-x86_64") == before


@pytest.mark.parametrize(
    ("library", "platform_plugin", "optional_libraries"),
    [
        ("bin/Qt6Core.dll", "qwindows.dll", ("bin/Qt6Pdf.dll",)),
        (
            "lib/libQt6Core.so.6",
            "libqxcb.so",
            ("lib/libQt6Pdf.so.6", "lib/libQt6Pdf.so.6.9.0"),
        ),
        (
            "lib/QtCore.framework/Versions/A/QtCore",
            "libqcocoa.dylib",
            ("lib/QtPdf.framework/Versions/A/QtPdf", "lib/libQt6Pdf.dylib"),
        ),
    ],
)
def test_qt_pruning_retains_native_platform_and_webengine_payload(
    tmp_path, library, platform_plugin, optional_libraries
):
    from payload_pruning import prune_qt_payload

    qt = tmp_path / "PyQt6/Qt6"
    retained = {
        library,
        f"plugins/platforms/{platform_plugin}",
        "resources/qtwebengine_resources.pak",
        "resources/icudtl.dat",
        "translations/qtbase_zh_CN.qm",
        "translations/qtwebengine_locales/en-US.pak",
        "translations/qtwebengine_locales/zh-CN.pak",
    }
    optional = {
        *optional_libraries,
        "qml/QtQuick/qmldir",
        "resources/qtwebengine_devtools_resources.pak",
        "translations/qtbase_fr.qm",
        "translations/qtwebengine_locales/fr.pak",
    }
    for relative in retained | optional:
        path = qt / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode("utf-8"))
    prune_qt_payload(tmp_path)
    assert {
        p.relative_to(qt).as_posix() for p in qt.rglob("*") if p.is_file()
    } == retained
    for relative in retained:
        assert (qt / relative).read_bytes() == relative.encode("utf-8")


@pytest.mark.parametrize("standard", ("Lib", "lib/python3.11"))
def test_inference_pruning_keeps_imports_native_libraries_and_metadata(
    tmp_path, standard
):
    import csv

    from payload_pruning import prune_runtime_payload

    library = tmp_path / standard
    site = library / "site-packages"
    kept = {
        "unittest/mock.py",
        "ssl.py",
        "ctypes/__init__.py",
        "site-packages/cv2/__init__.py",
        "site-packages/cv2/cv2.pyd",
        "site-packages/cv2/data/__init__.py",
        "site-packages/cv2/LICENSE.txt",
        "site-packages/opencv_python.libs/libavcodec.so.1",
        "site-packages/core/__init__.py",
        "site-packages/core-1.dist-info/METADATA",
    }
    optional = {
        "idlelib/main.py",
        "ensurepip/_bundled/pip.whl",
        "venv/__init__.py",
        "tkinter/__init__.py",
        "turtle.py",
        "turtledemo/demo.py",
        "test/test_os.py",
        "lib-dynload/_tkinter.so",
        "site-packages/pip/__init__.py",
        "site-packages/cv2/opencv_videoio_ffmpeg4130_64.dll",
        "site-packages/cv2/data/haarcascade_frontalface_default.xml",
        "site-packages/cv2/qt/fonts/font.ttf",
        "site-packages/cv2/samples/demo.py",
    }
    for relative in kept | optional:
        path = library / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
    native = tmp_path / "native/runtime.dll"
    native.parent.mkdir()
    native.write_bytes(b"GPU runtime")
    record = site / "core-1.dist-info/RECORD"
    with record.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(
            (name, "", "")
            for name in (
                "core/__init__.py",
                "cv2/opencv_videoio_ffmpeg4130_64.dll",
                "core-1.dist-info/RECORD",
            )
        )
    prune_runtime_payload(tmp_path)
    assert {
        p.relative_to(library).as_posix() for p in library.rglob("*") if p.is_file()
    } == (kept | {"site-packages/core-1.dist-info/RECORD"})
    with record.open(encoding="utf-8", newline="") as stream:
        assert {row[0] for row in csv.reader(stream)} == {
            "core/__init__.py",
            "core-1.dist-info/RECORD",
        }
    assert native.read_bytes() == b"GPU runtime"


def test_payload_pruning_refuses_paths_outside_staging(tmp_path):
    from payload_pruning import remove_owned

    owned = tmp_path / "staging"
    owned.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    file = outside / "data"
    file.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="escaped"):
        remove_owned(outside, owned)
    assert file.read_bytes() == b"preserve"


def test_linux_application_package_owns_its_launchers_and_dependencies(
    tmp_path, monkeypatch
):
    from dataclasses import replace
    from types import SimpleNamespace

    from PIL import Image

    from build_application_resources import assemble_linux_integration
    from runtime.component_inventory import inventory_component
    from test_deployment_transaction import installation
    from update import debian_packages

    root = tmp_path / "payload"
    manifest = installation(root)
    application = root / "application"
    monkeypatch.setattr(Image, "open", lambda *args: Image.new("RGBA", (256, 256)))
    assemble_linux_integration(application / "linux-integration")
    component = replace(
        manifest.component("application"), files=inventory_component(application)
    )
    inspected = []

    def build_deb(arguments, **kwargs):
        directory = Path(arguments[-2])
        control = (directory / "DEBIAN/control").read_text(encoding="utf-8")
        assert "Package: latexsnipper\n" in control and "Depends: libc6" in control
        assert (directory / "usr/bin/latexsnipper").is_file()
        assert (directory / "usr/lib/latexsnipper/LaTeXSnipper").is_file()
        assert (directory / "usr/share/applications/latexsnipper.desktop").is_file()
        assert (
            directory / "usr/lib/latexsnipper/application/data.bin"
        ).read_bytes() == b"application"
        inspected.append(True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(debian_packages.subprocess, "run", build_deb)
    debian_packages.build_package(application, component, tmp_path / "application.deb")
    assert inspected == [True]


def test_first_install_package_cleanup_preserves_the_active_transaction(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from update import debian_packages

    root = tmp_path / "usr/lib/latexsnipper"
    root.mkdir(parents=True)
    observed = []

    def purge(arguments, **kwargs):
        assert kwargs["env"]["LATEXSNIPPER_DEPLOYMENT_ACTIVE"] == "1"
        assert arguments[-3:] == [
            "latexsnipper",
            "latexsnipper-inference",
            "latexsnipper-models",
        ]
        observed.append(True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(debian_packages.subprocess, "run", purge)
    debian_packages.purge_packages(root, ["application", "inference", "models"])
    assert observed == [True]


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_linux_repair_can_back_up_damaged_package_metadata(
    tmp_path, monkeypatch, damage
):
    from dataclasses import replace
    from types import SimpleNamespace

    from runtime.component_inventory import inventory_component
    from test_deployment_transaction import installation
    from update import debian_packages
    from update.debian_transaction import DebianDeploymentTransaction

    staged = tmp_path / "staged"
    manifest = installation(staged)
    application = staged / "application"
    control = application / "linux-integration/DEBIAN/control"
    control.parent.mkdir(parents=True)
    control.write_text("Package: latexsnipper\nVersion: 0.0.0\n", encoding="utf-8")
    component = replace(
        manifest.component("application"), files=inventory_component(application)
    )
    manifest = replace(manifest, components=(component, *manifest.components[1:]))
    root = tmp_path / "prefix/usr/lib/latexsnipper"
    shutil.copytree(application, root / "application")
    damaged = root / "application/linux-integration"
    if damage == "missing":
        shutil.rmtree(damaged)
    else:
        (damaged / "DEBIAN/control").write_text("damaged", encoding="utf-8")
    packaged = []

    def build_deb(arguments, **kwargs):
        directory = Path(arguments[-2])
        assert (directory / "DEBIAN/control").read_text(encoding="utf-8") == (
            f"Package: latexsnipper\nVersion: 0+{component.content_sha256}\n"
        )
        packaged.append(Path(arguments[-1]).name)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(debian_packages.subprocess, "run", build_deb)
    transaction = DebianDeploymentTransaction(root)
    transaction.directory.mkdir()
    transaction._prepare(staged, manifest, manifest, [component])
    assert packaged == ["application.deb", "application.deb"]


@pytest.mark.parametrize(
    ("ort_minimum", "dependency_minimum", "expected"),
    [
        ("14_0", "12_0", "14.0"),
        ("14_0", "15_0", "15.0"),
    ],
)
def test_macos_minimum_covers_all_locked_wheels(
    ort_minimum, dependency_minimum, expected
):
    from distribution_inputs import macos_minimum_version

    sources = {
        "targets": {
            "macos-arm64": {"ort_cpu": {"url": f"ort-macosx_{ort_minimum}_arm64.whl"}}
        }
    }
    dependencies = {
        "targets": {
            "macos-arm64": [
                {
                    "artifact": {
                        "url": f"dependency-macosx_{dependency_minimum}_arm64.whl"
                    }
                }
            ]
        }
    }
    assert macos_minimum_version(sources, dependencies) == expected


def test_macos_bundle_build_uses_local_signatures(tmp_path, monkeypatch):
    import plistlib

    from PIL import Image

    from distribution_inputs import (
        load_dependencies,
        load_sources,
        macos_minimum_version,
    )
    from runtime.component_inventory import verify_component
    from test_deployment_transaction import installation
    from test_platform_deployment import retarget
    from update import macos_transaction

    layout = tmp_path / "layout"
    manifest = retarget(installation(layout), "macos")
    signed = []

    def native_tool(arguments, **kwargs):
        if arguments[0] == "clang":
            assert f"-mmacosx-version-min={minimum}" in arguments
        if arguments[0] in {"clang", "iconutil"}:
            Path(arguments[arguments.index("-o") + 1]).write_bytes(b"native fixture")
        elif arguments[0] == "codesign":
            signed.append(
                (arguments[arguments.index("--sign") + 1], Path(arguments[-1]))
            )

    checked = []
    sources = load_sources(ROOT / "packaging/runtime/sources.lock.json")
    dependencies = load_dependencies(
        ROOT / "packaging/runtime/dependencies.lock.json", sources
    )
    minimum = macos_minimum_version(sources, dependencies)
    monkeypatch.setattr(Image, "open", lambda *args: Image.new("RGBA", (256, 256)))
    monkeypatch.setattr(build, "run", native_tool)
    monkeypatch.setattr(macos_transaction, "verify_bundle", checked.append)
    bundle = build.create_macos_bundle(layout, manifest)
    with (bundle / "Contents/Info.plist").open("rb") as stream:
        assert plistlib.load(stream)["LSMinimumSystemVersion"] == minimum
    assert checked == [bundle]
    assert signed == [("-", bundle / "Contents/MacOS/LaTeXSnipper"), ("-", bundle)]
    for component in manifest.components:
        assert not verify_component(
            bundle / "Contents/Resources/desktop" / component.name, component
        )


def test_signed_windows_installer_replaces_only_the_carrier_identity(tmp_path):
    from release_artifacts import finalize_windows
    from runtime.component_inventory import file_sha256
    from runtime.distribution_manifest import DistributionManifest
    from test_deployment_transaction import installation
    from update.deployment_transaction import atomic_json

    distribution = installation(tmp_path / "layout")
    output, signed = tmp_path / "output", tmp_path / "signed"
    output.mkdir()
    signed.mkdir()
    filename = f"LaTeXSnipper_{distribution.version}_windows_x86_64_cpu.exe"
    (signed / filename).write_bytes(b"signed carrier")
    metadata = output / "distribution-windows-x86_64-cpu.json"
    atomic_json(metadata, distribution.to_dict())
    finalize_windows(output, signed)
    final = DistributionManifest.load(metadata)
    assert final.components == distribution.components
    assert final.installer is not None
    assert final.installer.sha256 == file_sha256(signed / filename)
    assert (output / filename).read_bytes() == b"signed carrier"
