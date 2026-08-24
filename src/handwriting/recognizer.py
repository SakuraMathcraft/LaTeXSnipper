from __future__ import annotations

from PIL import Image, ImageFilter
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage

from backend.external_model import ExternalModelClient, ExternalModelConfig
from recognition.error_messages import recognition_error_code_user_message, recognition_failure_user_message
from recognition.image_input import image_from_qimage, validated_rgb_image
from recognition.jobs import JobSource, RecognitionItemInput, RecognitionJobCoordinator

_UPSCALE_MIN_DIM = 120
_UPSCALE_TARGET_DIM = 220


def qimage_to_pil(image: QImage) -> Image.Image:
    """Normalize a handwriting canvas through the shared image boundary."""
    pil = image_from_qimage(image)
    if pil.width < _UPSCALE_MIN_DIM or pil.height < _UPSCALE_MIN_DIM:
        scale = max(2.0, _UPSCALE_TARGET_DIM / max(1, min(pil.width, pil.height)))
        pil = pil.resize(
            (max(1, int(pil.width * scale)), max(1, int(pil.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return pil


def enhance_stroke_image(pil: Image.Image) -> Image.Image:
    return pil.filter(ImageFilter.UnsharpMask(radius=0.8, percent=60, threshold=2))


class HandwritingRecognitionWorker(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        model_wrapper,
        image: QImage,
        model_name: str = "mathcraft",
        external_config: ExternalModelConfig | None = None,
        coordinator: RecognitionJobCoordinator | None = None,
    ):
        super().__init__()
        self.model_wrapper = model_wrapper
        self.image = image
        self.model_name = model_name
        self.external_config = external_config
        self.coordinator = coordinator
        self._job_id: str | None = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        if self.coordinator is not None and self._job_id:
            try:
                self.coordinator.cancel(self._job_id, principal_id="desktop-handwriting")
            except Exception:
                pass

    def run(self) -> None:
        try:
            if self._cancelled:
                self.failed.emit("已取消")
                return
            pil_img = qimage_to_pil(self.image)
            pil_img = enhance_stroke_image(pil_img)
            model_name = str(self.model_name or "mathcraft").strip().lower()
            if model_name == "external_model":
                if self.external_config is None:
                    self.failed.emit("外部模型未配置")
                    return
                if self.coordinator is None:
                    result_obj = ExternalModelClient(self.external_config).predict(pil_img)
                    result = result_obj.best_text(self.external_config.resolved_output_mode()).strip()
                else:
                    mode = {
                        "ocr_formula_v1": "formula",
                        "ocr_text_v1": "text",
                    }.get(self.external_config.prompt_template, "mixed")
                    job = self.coordinator.submit(
                        [RecognitionItemInput(image=validated_rgb_image(pil_img))],
                        principal_id="desktop-handwriting",
                        source=JobSource.HANDWRITING,
                        mode=mode,
                        timeout_seconds=self.external_config.normalized_timeout(),
                        input_type="handwriting_canvas",
                        backend="external",
                        external_config=self.external_config,
                    )
                    self._job_id = job["id"]
                    if self._cancelled:
                        self.coordinator.cancel(self._job_id, principal_id="desktop-handwriting")
                    snapshot = self.coordinator.wait(
                        job["id"], principal_id="desktop-handwriting", timeout=None
                    )
                    item = snapshot["items"][0]
                    if item["state"] != "completed":
                        error = item.get("error") or {}
                        raise RuntimeError(
                            recognition_error_code_user_message(error.get("code"), "external_model")
                        )
                    result = str(item["text"]).strip()
            else:
                if self.coordinator is None:
                    result = (self.model_wrapper.predict(pil_img, model_name=model_name) or "").strip()
                else:
                    mode = {
                        "mathcraft": "formula",
                        "mathcraft_text": "text",
                        "mathcraft_mixed": "mixed",
                    }.get(model_name, "formula")
                    job = self.coordinator.submit(
                        [RecognitionItemInput(image=validated_rgb_image(pil_img))],
                        principal_id="desktop-handwriting",
                        source=JobSource.HANDWRITING,
                        mode=mode,
                        timeout_seconds=300,
                        input_type="handwriting_canvas",
                    )
                    self._job_id = job["id"]
                    if self._cancelled:
                        self.coordinator.cancel(self._job_id, principal_id="desktop-handwriting")
                    snapshot = self.coordinator.wait(
                        job["id"], principal_id="desktop-handwriting", timeout=None
                    )
                    item = snapshot["items"][0]
                    if item["state"] != "completed":
                        error = item.get("error") or {}
                        raise RuntimeError(recognition_error_code_user_message(error.get("code"), "mathcraft"))
                    result = str(item["text"]).strip()

            if not str(result or "").strip():
                self.failed.emit("识别结果为空")
                return
            self.finished.emit(str(result).strip())
        except Exception as exc:
            backend = "external_model" if str(self.model_name).strip().lower() == "external_model" else "mathcraft"
            self.failed.emit(recognition_failure_user_message(exc, backend))
