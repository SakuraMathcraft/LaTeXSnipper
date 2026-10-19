"""Exercise live Qt update state, cancellation and independent-process handoff."""

import os
import threading
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication

from runtime.distribution_manifest import Artifact, ReleaseCatalog
from test_deployment_transaction import installation
from update import component_controller as controller_module
from update.component_controller import ComponentUpdateController
from update.component_release import ReleaseInfo, VerifiedRelease
from update.deployment_transaction import atomic_json
from update.update_dialog import ComponentUpdateDialog, check_update_dialog


@pytest.fixture(scope="session")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication(["component-update-tests"])


def pump(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    assert predicate()


@pytest.fixture
def updates(tmp_path, monkeypatch):
    root, staged = tmp_path / "installed", tmp_path / "release"
    current = installation(root)
    target = installation(staged, "4.0.0", {"application": b"new"})
    target = replace(
        target, installer=Artifact("https://example.com/installer.exe", "f" * 64, 100)
    )
    release = VerifiedRelease(
        ReleaseCatalog(target.version, (target,)),
        target.release_tag,
        "Changes",
        "https://example.com/release",
    )
    resources = SimpleNamespace(root=root, manifest=current)
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(controller_module, "app_cache_dir", lambda: cache)
    monkeypatch.setattr(controller_module, "installed_resources", lambda: resources)
    monkeypatch.setattr(
        controller_module, "fetch_component_release", lambda *args, **kwargs: release
    )
    monkeypatch.setattr(
        controller_module,
        "fetch_release_info",
        lambda: ReleaseInfo(release.tag, "**Changes**", release.url),
    )
    return resources, release, cache


def test_controller_plans_business_update_and_waits_for_helper_readiness(
    app, updates, monkeypatch
):
    resources, release, cache = updates
    controller = ComponentUpdateController()
    states = []
    controller.changed.connect(lambda state, data: states.append(state))

    def prepare(root, target, output, download_cache, **kwargs):
        assert root == resources.root and target == release.catalog.distributions[0]
        output.mkdir()

    monkeypatch.setattr(controller_module, "prepare_components", prepare)
    request = cache / "request.json"
    atomic_json(request, {})
    monkeypatch.setattr(controller_module, "launch_deployment", lambda *_args: request)
    controller.check()
    pump(app, lambda: "available" in states)
    assert [item.name for item in controller.plan.downloads] == ["application"]
    controller.prepare()
    pump(app, lambda: "ready" in states)
    controller.deploy()
    pump(app, lambda: "handoff" in states)
    assert controller.busy
    atomic_json(cache / "deployment-result.json", {"state": "ready"})
    pump(app, lambda: "handoff-ready" in states)
    assert not controller.busy
    controller.close()


def test_closed_controller_ignores_late_release_result(app, updates, monkeypatch):
    _, release, _ = updates
    entered, released = threading.Event(), threading.Event()

    def fetch(*args, **kwargs):
        entered.set()
        assert released.wait(3)
        return release

    monkeypatch.setattr(controller_module, "fetch_component_release", fetch)
    controller = ComponentUpdateController()
    states = []
    controller.changed.connect(lambda state, data: states.append(state))
    controller.check()
    assert entered.wait(1)
    controller.close()
    released.set()
    pump(app, lambda: not controller.busy)
    assert states == ["checking"]


def test_base_change_offers_complete_installation(app, updates, monkeypatch):
    _, latest, _ = updates
    target = replace(latest.catalog.distributions[0], base_id="2" * 64)
    release = replace(latest, catalog=ReleaseCatalog(target.version, (target,)))
    monkeypatch.setattr(
        controller_module, "fetch_component_release", lambda *args, **kwargs: release
    )
    dialog = ComponentUpdateDialog()
    pump(app, lambda: not dialog.controller.busy)
    assert dialog.controller.plan.installer_required
    assert not dialog.action.isEnabled() and dialog.link.isEnabled()
    dialog.close()


def test_failed_handoff_releases_helpers_and_staged_payloads(app, updates, monkeypatch):
    from runtime import deployment_feedback

    resources, _, cache = updates
    monkeypatch.setattr(deployment_feedback, "app_cache_dir", lambda: cache)
    directory = cache / "component-update-failed"
    staged = directory / "staged"
    staged.mkdir(parents=True)
    task = cache / "deployment-failed"
    task.mkdir()
    request = task / "request.json"
    atomic_json(
        request, {"root": str(resources.root), "staged": str(staged), "recover": False}
    )
    atomic_json(
        task / "deployment-result.json",
        {"state": "failed", "error": "rejected before exit"},
    )
    monkeypatch.setattr(controller_module, "launch_deployment", lambda *args: request)
    controller = ComponentUpdateController()
    controller.resources, controller._directory, controller.staged = (
        resources,
        directory,
        staged,
    )
    states = []
    controller.changed.connect(lambda state, data: states.append(state))
    controller.deploy()
    pump(app, lambda: "failed" in states)
    controller.close()
    pump(app, lambda: not task.exists() and not directory.exists())


def test_update_dialog_can_be_closed_and_immediately_reopened(app, updates):
    first = check_update_dialog()
    pump(app, lambda: not first.controller.busy)
    first.close()
    second = check_update_dialog()
    assert second is not first and second.isVisible()
    pump(app, lambda: not second.controller.busy)
    second.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_source_update_view_does_not_request_environment_installation(
    app, updates, monkeypatch
):
    monkeypatch.setattr(controller_module, "installed_resources", lambda: None)
    dialog = ComponentUpdateDialog()
    pump(app, lambda: dialog._state == "source")
    assert not dialog.action.isEnabled() and dialog.link.isEnabled()
    assert "Changes" in dialog.details.toPlainText()
    assert not dialog.busy_progress.isVisible()
    dialog.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_update_loading_uses_animated_bar_and_keeps_release_notes_on_catalog_failure(
    app, updates, monkeypatch
):
    gate = threading.Event()
    _, release, _ = updates

    def check(*args, on_release=None, **kwargs):
        assert gate.wait(3)
        on_release(ReleaseInfo(release.tag, "**Release content**", release.url))
        raise ValueError("Component catalog unavailable")

    monkeypatch.setattr(controller_module, "fetch_component_release", check)
    dialog = ComponentUpdateDialog()
    try:
        dialog.show()
        assert dialog.busy_progress.isVisible()
        assert not dialog.progress.isVisible()
        assert (
            "发布" in dialog.details.toPlainText()
            or "Release" in dialog.details.toPlainText()
        )
        gate.set()
        pump(app, lambda: dialog._state == "failed")
        assert "Release content" in dialog.details.toPlainText()
        assert not dialog.busy_progress.isVisible()
        dialog._render("downloading", {})
        dialog._render("progress", {"done": 5, "total": 10})
        assert dialog.progress.isVisible() and dialog.progress.value() == 50
        dialog._render("verifying", {})
        assert dialog.busy_progress.isVisible() and not dialog.progress.isVisible()
    finally:
        gate.set()
        dialog.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
