from __future__ import annotations

import threading
import time

import pytest
from PIL import Image

from backend.external_model.schemas import ExternalModelConfig
from integration.automation.auth import (
    EXTERNAL_PERMISSION,
    MATHCRAFT_PERMISSION,
    AutomationApiAuth,
)
from integration.automation.contracts import AutomationApiError, AutomationLimits, validate_mode
from recognition.jobs import JobSource, RecognitionItemInput, RecognitionJobCoordinator, RecognitionJobError


def _image(width: int = 8, height: int = 8) -> RecognitionItemInput:
    return RecognitionItemInput(Image.new("RGB", (width, height), "white"), "input.png")


def test_auth_keeps_local_and_remote_credentials_isolated() -> None:
    auth = AutomationApiAuth(local_token="local", remote_key="remote")
    local = auth.authenticate("Bearer local")
    remote = auth.authenticate("Bearer remote")

    assert local is not None and local.kind == "local"
    assert local.allows(MATHCRAFT_PERMISSION) and local.allows(EXTERNAL_PERMISSION)
    assert remote is not None and remote.kind == "remote"
    assert remote.allows(MATHCRAFT_PERMISSION) and not remote.allows(EXTERNAL_PERMISSION)
    assert auth.authenticate("Bearer wrong") is None
    allowed_remote = AutomationApiAuth(
        local_token="local-2",
        remote_key="remote-2",
        remote_external_enabled=True,
    ).authenticate("Bearer remote-2")
    assert allowed_remote is not None and allowed_remote.allows(EXTERNAL_PERMISSION)


def test_invalid_recognition_mode_has_stable_error() -> None:
    with pytest.raises(AutomationApiError) as raised:
        validate_mode("document")
    assert raised.value.code == "invalid_mode"


def test_coordinator_serializes_concurrent_inference_and_preserves_order() -> None:
    active = 0
    maximum_active = 0
    lock = threading.Lock()

    def predict(image, mode: str) -> str:
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return f"{mode}:{image.width}"

    coordinator = RecognitionJobCoordinator(predict)
    try:
        jobs = [
            coordinator.submit(
                [_image(index + 1), _image(index + 10)],
                principal_id=f"client-{index}",
                source=JobSource.LOCAL_API,
                mode="formula",
                timeout_seconds=5,
            )
            for index in range(4)
        ]
        snapshots = [
            coordinator.wait(job["id"], principal_id=f"client-{index}", timeout=5)
            for index, job in enumerate(jobs)
        ]
        assert maximum_active == 1
        assert [[item["text"] for item in job["items"]] for job in snapshots] == [
            [f"formula:{index + 1}", f"formula:{index + 10}"] for index in range(4)
        ]
    finally:
        coordinator.stop()


def test_cancel_interrupts_a_running_mathcraft_worker() -> None:
    class InterruptiblePredictor:
        def __init__(self) -> None:
            self.started = threading.Event()
            self.release = threading.Event()
            self.interruptions = 0

        def predict_result(self, _image, *, model_name: str):
            self.started.set()
            self.release.wait(2)
            return {"text": model_name}

        def _stop_mathcraft_worker(self) -> None:
            self.interruptions += 1
            self.release.set()

    predictor = InterruptiblePredictor()
    coordinator = RecognitionJobCoordinator(predictor)
    try:
        job = coordinator.submit(
            [_image()],
            principal_id="desktop-ui",
            source=JobSource.UI,
            mode="formula",
            timeout_seconds=5,
        )
        assert predictor.started.wait(1)

        coordinator.cancel(job["id"], principal_id="desktop-ui")
        snapshot = coordinator.wait(job["id"], principal_id="desktop-ui", timeout=1)

        assert predictor.interruptions == 1
        assert snapshot["state"] == "canceled"
        assert snapshot["error"]["code"] == "canceled"
    finally:
        predictor.release.set()
        coordinator.stop()


def test_external_executor_is_serial_and_does_not_block_mathcraft() -> None:
    external_active = 0
    external_maximum = 0
    external_started = threading.Event()
    release_external = threading.Event()

    def predict_external(_image, _config) -> str:
        nonlocal external_active, external_maximum
        external_active += 1
        external_maximum = max(external_maximum, external_active)
        external_started.set()
        release_external.wait(2)
        external_active -= 1
        return "external"

    config = ExternalModelConfig(base_url="http://127.0.0.1:11434", model_name="vision")
    coordinator = RecognitionJobCoordinator(
        lambda _image, _mode: "mathcraft",
        external_config_provider=lambda: config,
        external_predictor=predict_external,
    )
    try:
        external_jobs = [
            coordinator.submit(
                [_image()],
                principal_id="external",
                source=JobSource.LOCAL_API,
                backend="external",
                mode="formula",
                timeout_seconds=5,
            )
            for _ in range(2)
        ]
        assert external_started.wait(1)
        mathcraft = coordinator.submit(
            [_image()],
            principal_id="mathcraft",
            source=JobSource.LOCAL_API,
            mode="formula",
            timeout_seconds=5,
        )
        assert coordinator.wait(mathcraft["id"], principal_id="mathcraft", timeout=1)["state"] == "completed"
        release_external.set()
        for job in external_jobs:
            snapshot = coordinator.wait(job["id"], principal_id="external", timeout=2)
            assert snapshot["backend"] == "external"
            assert snapshot["items"][0]["text"] == "external"
        assert external_maximum == 1
    finally:
        release_external.set()
        coordinator.stop()


def test_external_job_uses_immutable_configuration_snapshot() -> None:
    release = threading.Event()
    config = ExternalModelConfig(base_url="http://127.0.0.1:11434", model_name="before")

    def predict(_image, snapshot) -> str:
        release.wait(1)
        return snapshot.model_name

    coordinator = RecognitionJobCoordinator(
        lambda _image, _mode: "unused",
        external_config_provider=lambda: config,
        external_predictor=predict,
    )
    try:
        job = coordinator.submit(
            [_image()],
            principal_id="p",
            source=JobSource.LOCAL_API,
            backend="external",
            mode="formula",
            timeout_seconds=5,
        )
        config.model_name = "after"
        release.set()
        snapshot = coordinator.wait(job["id"], principal_id="p", timeout=2)
        assert snapshot["items"][0]["text"] == "before"
    finally:
        release.set()
        coordinator.stop()


def test_only_mathcraft_executor_applies_mathcraft_resize_limits() -> None:
    seen: dict[str, tuple[int, int]] = {}
    config = ExternalModelConfig(base_url="http://127.0.0.1:11434", model_name="vision")

    def mathcraft(image, _mode):
        seen["mathcraft"] = image.size
        return "mathcraft"

    def external(image, _config):
        seen["external"] = image.size
        return "external"

    coordinator = RecognitionJobCoordinator(
        mathcraft,
        external_config_provider=lambda: config,
        external_predictor=external,
    )
    source = _image(3000, 100)
    try:
        jobs = (
            coordinator.submit(
                [source], principal_id="m", source=JobSource.UI, mode="formula", timeout_seconds=5
            ),
            coordinator.submit(
                [source],
                principal_id="e",
                source=JobSource.UI,
                mode="formula",
                timeout_seconds=5,
                backend="external",
            ),
        )
        coordinator.wait(jobs[0]["id"], principal_id="m", timeout=2)
        coordinator.wait(jobs[1]["id"], principal_id="e", timeout=2)
        assert max(seen["mathcraft"]) <= 2400
        assert seen["external"] == (3000, 100)
    finally:
        coordinator.stop()


def test_mode_capability_and_partial_batch_failure_are_stable() -> None:
    class Predictor:
        @staticmethod
        def supports_mode(mode: str) -> bool:
            return mode != "text"

        @staticmethod
        def predict_result(image, *, model_name: str):
            if image.width == 2:
                raise RuntimeError("synthetic failure")
            return {"text": f"{model_name}:{image.width}"}

    coordinator = RecognitionJobCoordinator(Predictor())
    try:
        with pytest.raises(RecognitionJobError) as unsupported:
            coordinator.submit(
                [_image()],
                principal_id="p",
                source=JobSource.LOCAL_API,
                mode="text",
                timeout_seconds=5,
            )
        assert unsupported.value.code == "mode_unsupported"

        job = coordinator.submit(
            [_image(1, 1), _image(2, 1), _image(3, 1)],
            principal_id="p",
            source=JobSource.LOCAL_API,
            mode="formula",
            timeout_seconds=5,
        )
        snapshot = coordinator.wait(job["id"], principal_id="p", timeout=2)
        assert snapshot["state"] == "completed"
        assert [item["state"] for item in snapshot["items"]] == ["completed", "failed", "completed"]
        assert snapshot["items"][1]["error"]["code"] == "internal_error"
    finally:
        coordinator.stop()


def test_mathcraft_jobs_can_lazy_load_an_unwarmed_model() -> None:
    class Predictor:
        @staticmethod
        def is_model_ready(_model_name: str) -> bool:
            return False

        @staticmethod
        def predict_result(image, *, model_name: str):
            return {"text": f"{model_name}:{image.width}"}

    coordinator = RecognitionJobCoordinator(Predictor())
    try:
        job = coordinator.submit(
            [_image()],
            principal_id="p",
            source=JobSource.LOCAL_API,
            mode="formula",
            timeout_seconds=5,
        )
        snapshot = coordinator.wait(job["id"], principal_id="p", timeout=2)
        assert snapshot["state"] == "completed"
    finally:
        coordinator.stop()


def test_trusted_external_operations_share_the_external_serial_boundary() -> None:
    active = 0
    maximum = 0
    lock = threading.Lock()

    def enter() -> str:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return "ok"

    config = ExternalModelConfig(base_url="http://127.0.0.1:11434", model_name="vision")
    coordinator = RecognitionJobCoordinator(
        lambda _image, _mode: "unused",
        external_config_provider=lambda: config,
        external_predictor=lambda _image, _config: enter(),
    )
    operation_thread = threading.Thread(target=lambda: coordinator.run_external_operation(enter))
    try:
        operation_thread.start()
        job = coordinator.submit(
            [_image()],
            principal_id="p",
            source=JobSource.LOCAL_API,
            backend="external",
            mode="formula",
            timeout_seconds=5,
        )
        assert coordinator.wait(job["id"], principal_id="p", timeout=2)["state"] == "completed"
        operation_thread.join(timeout=2)
        assert maximum == 1
    finally:
        operation_thread.join(timeout=2)
        coordinator.stop()


def test_coordinator_enforces_principal_ownership_and_active_image_memory() -> None:
    blocker = threading.Event()
    coordinator = RecognitionJobCoordinator(
        lambda _image, _mode: blocker.wait(1) or "ok",
        limits=AutomationLimits(max_queued_jobs=2, max_queued_image_bytes=300),
    )
    try:
        job = coordinator.submit(
            [_image(10, 10)],
            principal_id="owner",
            source=JobSource.LOCAL_API,
            mode="formula",
            timeout_seconds=5,
        )
        with pytest.raises(RecognitionJobError) as hidden:
            coordinator.get(job["id"], principal_id="other")
        assert hidden.value.code == "job_not_found"
        with pytest.raises(RecognitionJobError) as full:
            coordinator.submit(
                [_image(10, 10)],
                principal_id="owner",
                source=JobSource.LOCAL_API,
                mode="formula",
                timeout_seconds=5,
            )
        assert full.value.code == "queue_full"
    finally:
        blocker.set()
        coordinator.stop()


def test_queued_and_running_cancellation_have_stable_terminal_state() -> None:
    started = threading.Event()
    release = threading.Event()

    def predict(_image, _mode: str) -> str:
        started.set()
        release.wait(2)
        return "result"

    coordinator = RecognitionJobCoordinator(predict)
    try:
        running = coordinator.submit(
            [_image()], principal_id="p", source=JobSource.UI, mode="formula", timeout_seconds=5
        )
        assert started.wait(1)
        queued = coordinator.submit(
            [_image()], principal_id="p", source=JobSource.UI, mode="formula", timeout_seconds=5
        )
        assert coordinator.cancel(queued["id"], principal_id="p")["state"] == "canceled"
        coordinator.cancel(running["id"], principal_id="p")
        release.set()
        assert coordinator.wait(running["id"], principal_id="p", timeout=2)["state"] == "canceled"
    finally:
        release.set()
        coordinator.stop()


def test_next_result_timeout_and_completed_ttl_are_enforced() -> None:
    current = [10.0]
    limits = AutomationLimits(completed_job_ttl_seconds=2, max_retained_jobs=2)
    coordinator = RecognitionJobCoordinator(lambda _image, _mode: "ok", limits=limits, clock=lambda: current[0])
    try:
        waiter = coordinator.create_next_result_job(
            principal_id="p", source=JobSource.LOCAL_API, timeout_seconds=1
        )
        current[0] = 11.1
        snapshot = coordinator.get(waiter["id"], principal_id="p")
        assert snapshot["state"] == "failed"
        assert snapshot["error"]["code"] == "timeout"
        current[0] = 13.2
        with pytest.raises(RecognitionJobError) as expired:
            coordinator.get(waiter["id"], principal_id="p")
        assert expired.value.code == "job_expired"
    finally:
        coordinator.stop()


def test_next_result_is_published_once_and_external_secrets_are_released() -> None:
    config = ExternalModelConfig(
        base_url="https://example.invalid",
        model_name="vision",
        api_key="secret",
    )
    coordinator = RecognitionJobCoordinator(
        lambda _image, _mode: "unused",
        external_config_provider=lambda: config,
        external_predictor=lambda _image, _config: "ok",
    )
    try:
        waiter = coordinator.create_next_result_job(
            principal_id="p",
            source=JobSource.LOCAL_API,
            timeout_seconds=5,
        )
        with pytest.raises(RecognitionJobError) as busy:
            coordinator.create_next_result_job(
                principal_id="p",
                source=JobSource.LOCAL_API,
                timeout_seconds=5,
            )
        assert busy.value.code == "next_result_busy"
        assert coordinator.publish_next_result("x^2", backend="mathcraft", mode="formula")
        completed = coordinator.get(waiter["id"], principal_id="p")
        assert completed["state"] == "completed"
        assert completed["items"][0]["text"] == "x^2"
        assert not coordinator.publish_next_result("ignored", backend="mathcraft", mode="formula")

        job = coordinator.submit(
            [_image()],
            principal_id="p",
            source=JobSource.LOCAL_API,
            backend="external",
            mode="formula",
            timeout_seconds=5,
        )
        assert coordinator.wait(job["id"], principal_id="p", timeout=2)["state"] == "completed"
        assert coordinator._jobs[job["id"]].backend_config is None
    finally:
        coordinator.stop()


def test_next_result_failure_preserves_specific_empty_result_code() -> None:
    coordinator = RecognitionJobCoordinator(lambda _image, _mode: "unused")
    try:
        waiter = coordinator.create_next_result_job(
            principal_id="office",
            source=JobSource.OFFICE,
            timeout_seconds=5,
        )

        assert coordinator.fail_next_result("未识别到公式内容", code="empty_formula")
        snapshot = coordinator.get(waiter["id"], principal_id="office")

        assert snapshot["state"] == "failed"
        assert snapshot["error"] == {
            "code": "empty_formula",
            "message": "未识别到公式内容",
        }
    finally:
        coordinator.stop()
