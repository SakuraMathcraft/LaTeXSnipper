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
    for name in ("sources.lock.json", "resources.lock.json", "dependencies.lock.json"):
        shutil.copy2(ROOT / "packaging/runtime" / name, locks / name)
    monkeypatch.setattr(build, "ROOT", tmp_path)
    return tmp_path


@pytest.mark.parametrize(
    ("target", "path", "affected"),
    [
        ("windows-x86_64", "scripts/normalize_windows_crt.ps1", {"runtime"}),
        ("linux-x86_64", "scripts/linux_hotkey_packaging.py", {"runtime"}),
        ("linux-x86_64", "packaging/debian/DEBIAN/control", set()),
        ("linux-x86_64", "requirements.txt", {"runtime"}),
        ("macos-arm64", "requirements.txt", {"runtime", "base"}),
        ("windows-x86_64", "mathcraft_ocr/vendor/LICENSE.onnx", set()),
        (
            "windows-x86_64",
            "scripts/payload_pruning.py",
            {"inference-cpu", "inference-gpu"},
        ),
        (
            "macos-arm64",
            "packaging/macos/entitlements.plist",
            {"runtime", "inference-cpu", "maintenance", "base"},
        ),
        (
            "windows-x86_64",
            "src/runtime/inference_probe.py",
            {"inference-cpu", "inference-gpu"},
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


def test_model_identity_depends_only_on_locked_model_bytes(inputs):
    import json

    before = build.build_inputs("windows-x86_64")
    path = inputs / "packaging/runtime/resources.lock.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    model = next(iter(data["models"].values()))
    model["sha256"] = "f" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    after = build.build_inputs("windows-x86_64")
    assert {name for name in before if before[name] != after[name]} == {"models"}


def test_gpu_library_change_preserves_cpu_and_gui_caches(inputs):
    import json

    before = build.build_inputs("windows-x86_64")
    path = inputs / "packaging/runtime/sources.lock.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["targets"]["windows-x86_64"]["minimum_driver"] = [999, 0]
    path.write_text(json.dumps(data), encoding="utf-8")
    after = build.build_inputs("windows-x86_64")
    assert {name for name in before if before[name] != after[name]} == {"inference-gpu"}


def test_maintenance_fingerprint_follows_transitive_source_imports(inputs):
    entry = inputs / "src/maintenance_main.py"
    entry.parent.mkdir(parents=True)
    helper = entry.parent / "helper.py"
    entry.write_text("from helper import run", encoding="utf-8")
    helper.write_text("def run(): return 1", encoding="utf-8")
    before = build.build_inputs("windows-x86_64")
    helper.write_text("def run(): return 2", encoding="utf-8")
    after = build.build_inputs("windows-x86_64")
    assert {name for name in before if before[name] != after[name]} == {"maintenance"}


def test_maintenance_import_closure_covers_packages_relative_and_lazy_imports(tmp_path):
    from release_build_inputs import source_dependencies

    files = {
        "src/entry.py": "from package import worker",
        "src/package/__init__.py": "from .metadata import VERSION",
        "src/package/metadata.py": "VERSION = '1'",
        "src/package/worker.py": "def run():\n    from .nested.helper import start",
        "src/package/nested/__init__.py": "",
        "src/package/nested/helper.py": "from ..metadata import VERSION",
        "src/unrelated.py": "VALUE = 2",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    assert {
        path.relative_to(tmp_path).as_posix()
        for path in source_dependencies(tmp_path, [tmp_path / "src/entry.py"])
    } == set(files) - {"src/unrelated.py"}


@pytest.mark.parametrize(
    ("target", "missing", "expected", "probed"),
    [
        (
            "windows-x86_64",
            set(),
            (False, False, False),
            {"runtime", "inference-cpu", "inference-gpu", "models", "maintenance"},
        ),
        (
            "linux-x86_64",
            {"maintenance"},
            (False, True, False),
            {"runtime", "inference-cpu", "inference-gpu", "models", "maintenance"},
        ),
        (
            "linux-x86_64",
            {"runtime", "inference-gpu"},
            (True, False, True),
            {"runtime", "inference-cpu", "inference-gpu", "models", "maintenance"},
        ),
        ("macos-arm64", set(), (False, False, False), {"base", "maintenance"}),
        (
            "macos-arm64",
            {"base"},
            (False, False, False),
            {"base", "maintenance", "runtime", "inference-cpu", "models"},
        ),
        (
            "macos-arm64",
            {"base", "runtime"},
            (True, False, True),
            {"base", "maintenance", "runtime", "inference-cpu", "models"},
        ),
    ],
)
def test_cache_plan_installs_only_tools_for_missing_payloads(
    inputs, monkeypatch, target, missing, expected, probed
):
    from argparse import Namespace

    import desktop_base_cache

    checked, flags = [], {}
    monkeypatch.setattr(build, "current_target", lambda: tuple(target.split("-")))
    monkeypatch.setattr(desktop_base_cache, "cache_tag", lambda name, *_: name)

    def exists(name):
        checked.append(name)
        return name not in missing

    monkeypatch.setattr(desktop_base_cache, "exists", exists)
    monkeypatch.setattr(build, "outputs", flags.update)
    args = Namespace(plan=inputs / "plan.json")
    plan = build.plan_build(args)
    assert set(checked) == probed
    assert len(checked) == len(probed)
    assert (
        tuple(
            flags[name]
            for name in ("gui_missing", "maintenance_missing", "native_missing")
        )
        == expected
    )
    assert build.load_plan(args) == plan


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
    from qt_payload import prune_qt_payload

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
    terminfo = tmp_path / "share/terminfo/e/eterm"
    terminfo.parent.mkdir(parents=True)
    terminfo.write_bytes(b"terminal database")
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
    assert not terminfo.exists()


def test_payload_pruning_refuses_paths_outside_staging(tmp_path):
    from payload_paths import remove_owned

    owned = tmp_path / "staging"
    owned.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    file = outside / "data"
    file.write_bytes(b"preserve")
    with pytest.raises(ValueError, match="escaped"):
        remove_owned(outside, owned)
    assert file.read_bytes() == b"preserve"


def test_qt_pruning_preserves_core_links_and_cleans_optional_aliases(tmp_path):
    from qt_payload import prune_qt_payload

    qt = tmp_path / "PyQt6/Qt6/lib"
    for module in ("QtCore", "QtWebSockets"):
        binary = qt / f"{module}.framework/Versions/A/{module}"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(module.encode("utf-8"))
        try:
            (tmp_path / module).symlink_to(binary.relative_to(tmp_path))
            (tmp_path / f"{module}.framework").symlink_to(
                binary.parents[2].relative_to(tmp_path), target_is_directory=True
            )
        except OSError as exc:
            pytest.skip(f"Symbolic links unavailable: {exc}")
    prune_qt_payload(tmp_path)
    assert {
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file() or path.is_symlink()
    } == {
        "PyQt6/Qt6/lib/QtCore.framework/Versions/A/QtCore",
        "QtCore",
        "QtCore.framework",
    }
    assert (tmp_path / "QtCore").read_bytes() == b"QtCore"


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
    component = replace(manifest.application, files=inventory_component(application))
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
    debian_packages.build_package(
        application,
        "application",
        component.content_sha256,
        tmp_path / "application.deb",
    )
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

    layout = tmp_path / "layout"
    manifest = retarget(installation(layout), "macos")
    fixed = layout / "LaTeXSnipperBase.bundle/Contents/Resources"
    fixed.mkdir(parents=True)
    for name in ("runtime", "inference", "models"):
        (layout / name).rename(fixed / name)
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

    sources = load_sources(ROOT / "packaging/runtime/sources.lock.json")
    dependencies = load_dependencies(
        ROOT / "packaging/runtime/dependencies.lock.json", sources
    )
    minimum = macos_minimum_version(sources, dependencies)
    monkeypatch.setattr(Image, "open", lambda *args: Image.new("RGBA", (256, 256)))
    monkeypatch.setattr(build, "run", native_tool)
    bundle = build.create_macos_bundle(layout, manifest)
    with (bundle / "Contents/Info.plist").open("rb") as stream:
        assert plistlib.load(stream)["LSMinimumSystemVersion"] == minimum
    assert signed[-2:] == [("-", bundle / "Contents/MacOS/LaTeXSnipper"), ("-", bundle)]
    assert not verify_component(
        bundle / "Contents/Resources/desktop/application", manifest.application
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
    assert final.application == distribution.application
    assert final.installer is not None
    assert final.installer.sha256 == file_sha256(signed / filename)
    assert (output / filename).read_bytes() == b"signed carrier"


@pytest.mark.parametrize("name", ["runtime", "maintenance"])
def test_fixed_resource_cold_build_and_verified_reuse(tmp_path, monkeypatch, name):
    from argparse import Namespace

    import desktop_base_cache

    created, saved = [], []
    monkeypatch.setattr(
        desktop_base_cache, "store", lambda directory, tag: saved.append(tag)
    )
    monkeypatch.setattr(build, "current_target", lambda: ("windows", "x86_64"))

    def create(payload):
        created.append(payload)
        payload.mkdir()
        (payload / "library.dll").write_bytes(b"locked dependency")

    args = Namespace(work=tmp_path)
    payload = build.reuse_payload(args, name, "a" * 64, create, available=False)
    assert len(created) == len(saved) == 1
    shutil.rmtree(payload)
    restored = build.reuse_payload(args, name, "a" * 64, create, available=True)
    assert (restored / "library.dll").read_bytes() == b"locked dependency"
    assert len(created) == len(saved) == 1
    archive = next((tmp_path / name).glob("*.zip"))
    archive.write_bytes(b"corrupt cached archive")
    shutil.rmtree(restored)
    with pytest.raises(ValueError, match="check"):
        build.reuse_payload(args, name, "a" * 64, create, available=True)


@pytest.mark.parametrize("target", ["windows-x86_64", "linux-x86_64", "macos-arm64"])
def test_assembly_reuses_verified_caches_and_merges_maintenance(
    tmp_path, monkeypatch, target
):
    from argparse import Namespace

    import build_application_resources
    import desktop_base_cache

    target_parts = tuple(target.split("-"))
    monkeypatch.setattr(build, "current_target", lambda: target_parts)
    monkeypatch.setattr(
        desktop_base_cache, "restore", lambda *_: pytest.fail("unexpected download")
    )
    monkeypatch.setattr(
        desktop_base_cache, "store", lambda *_: pytest.fail("unexpected build")
    )
    monkeypatch.setattr(
        build, "build_maintenance", lambda *_: pytest.fail("unexpected freeze")
    )
    args = Namespace(
        work=tmp_path / "desktop",
        models=tmp_path / "common-models",
        cache=tmp_path / "downloads",
        plan=tmp_path / "plan.json",
    )
    names = (
        ["base", "maintenance"]
        if target_parts[0] == "macos"
        else ["runtime", "inference-cpu", "inference-gpu", "models", "maintenance"]
    )
    keys = {name: "a" * 64 for name in names}
    for name in names:
        directory = (args.models if name == "models" else args.work) / name
        directory.mkdir(parents=True)
        source = tmp_path / f"source-{name}"
        source.mkdir()
        if name == "maintenance":
            (source / "bootstrap").mkdir()
            (source / "bootstrap/launcher").write_bytes(b"launcher")
            (source / "updater").write_bytes(b"updater")
        else:
            (source / "data").write_bytes(name.encode("utf-8"))
        component = build.package_component(
            source,
            directory,
            name.split("-")[0],
            "any-any" if name == "models" else target,
            name.split("-", 1)[1] if name.startswith("inference-") else "common",
            "https://github.com/SakuraMathcraft/LaTeXSnipper/releases/download/cache",
        )
        build.write_json(
            directory / "stamp.json",
            {"input": keys[name], "component": component.to_dict()},
        )
    build.write_json(
        args.plan,
        {
            "schema": 1,
            "target": target,
            "keys": keys,
            "available": dict.fromkeys(names, True),
        },
    )

    def business(options):
        options.application.mkdir(parents=True)
        (options.application / "main.py").write_bytes(b"business")

    monkeypatch.setattr(build_application_resources, "assemble", business)
    build.assemble(args)
    payload = args.work / "application/payload"
    assert (payload / "main.py").read_bytes() == b"business"
    assert (payload / "updater").read_bytes() == b"updater"
    assert (payload / "bootstrap/launcher").read_bytes() == b"launcher"
    for name in set(names) - {"maintenance"}:
        owner = args.models if name == "models" else args.work
        assert (owner / name / "payload/data").read_bytes() == name.encode("utf-8")


@pytest.mark.parametrize("outcome", ["missing", "forbidden", "draft", "published"])
def test_fixed_cache_rebuilds_only_when_missing(monkeypatch, outcome):
    from types import SimpleNamespace

    import desktop_base_cache

    monkeypatch.setattr(
        desktop_base_cache.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1 if outcome in {"missing", "forbidden"} else 0,
            stderr="release not found" if outcome == "missing" else "HTTP 403",
            stdout='{"isDraft":true}' if outcome == "draft" else '{"isDraft":false}',
        ),
    )
    if outcome == "missing":
        assert desktop_base_cache.exists("base") is False
    elif outcome == "draft":
        assert desktop_base_cache.exists("base") is True
    elif outcome == "published":
        with pytest.raises(ValueError, match="private draft"):
            desktop_base_cache.exists("base")
    else:
        with pytest.raises(ValueError, match="Cannot read"):
            desktop_base_cache.exists("base")


@pytest.mark.parametrize("system", ["win32", "linux", "darwin"])
def test_fixed_host_executes_business_and_worker_source(tmp_path, system):
    import subprocess

    desktop = (
        tmp_path / "LaTeXSnipper.app/Contents/Resources/desktop"
        if system == "darwin"
        else tmp_path
    )
    application = desktop / "application"
    application.mkdir(parents=True)
    worker = application / "worker/mathcraft_ocr"
    worker.mkdir(parents=True)
    (application / "business.py").write_text(
        "VALUE = 'business source'", encoding="utf-8"
    )
    (worker / "__init__.py").write_text("VALUE = 'worker source'", encoding="utf-8")
    output = tmp_path / "result.txt"
    (application / "main.py").write_text(
        "from pathlib import Path\nimport business, mathcraft_ocr\n"
        f"Path({str(output)!r}).write_text(business.VALUE + '/' + mathcraft_ocr.VALUE, encoding='utf-8')",
        encoding="utf-8",
    )
    executable = (
        tmp_path
        / "LaTeXSnipper.app/Contents/Frameworks/LaTeXSnipperBase.bundle/Contents/Resources/runtime/LaTeXSnipper"
        if system == "darwin"
        else desktop / "runtime/LaTeXSnipper"
    )
    code = "import sys, runpy; sys.platform = sys.argv[1]; sys.executable = sys.argv[2]; runpy.run_path(sys.argv[3], run_name='__main__')"
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            "utf8",
            "-c",
            code,
            system,
            str(executable),
            str(ROOT / "packaging/runtime/gui_entry.py"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8") == "business source/worker source"
