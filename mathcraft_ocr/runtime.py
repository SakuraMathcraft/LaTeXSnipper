# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rapidocr.utils.process_img import get_rotate_crop_image

from .adapters.formula_detector import detect_formula_boxes, warmup_formula_detector
from .adapters.formula_recognizer import recognize_formula_image, warmup_formula_recognizer
from .adapters.text_detector import detect_text_boxes, warmup_text_detector
from .adapters.text_recognizer import (
    recognize_pp_text_lines,
    warmup_pp_text_recognizer,
)
from .cache import inspect_manifest_cache, resolve_cache_dir
from .doctor import DoctorReport, run_doctor
from .downloader import download_model_archive
from .errors import ModelCacheError
from .image import load_image_rgb, rgb_to_bgr
from .layout import (
    box_to_points,
    group_blocks_into_lines,
    mask_boxes,
    merge_blocks_text,
    points_to_box,
    split_text_box_around_formulas,
)
from .manifest import Manifest, load_manifest
from .providers import ProviderInfo
from .results import Box4P, FormulaRecognitionResult, MathCraftBlock, MixedRecognitionResult, OCRRegion


FORMULA_DETECTOR_ID = "mathcraft-formula-det"
FORMULA_RECOGNIZER_ID = "mathcraft-formula-rec"
TEXT_DETECTOR_ID = "mathcraft-text-det"
TEXT_RECOGNIZER_ID = "mathcraft-text-rec"
EN_TEXT_DETECTOR_ID = "mathcraft-text-det-lite-en"
EN_TEXT_RECOGNIZER_ID = "mathcraft-text-rec-lite-en"

PROFILE_MODEL_IDS = {
    "formula": (FORMULA_DETECTOR_ID, FORMULA_RECOGNIZER_ID),
    "mixed": (
        FORMULA_DETECTOR_ID,
        FORMULA_RECOGNIZER_ID,
        TEXT_DETECTOR_ID,
        TEXT_RECOGNIZER_ID,
    ),
}


@dataclass(frozen=True)
class WarmupComponentStatus:
    model_id: str
    ready: bool
    detail: str = ""


@dataclass(frozen=True)
class WarmupPlan:
    profile: str
    required_models: tuple[str, ...]
    missing_models: tuple[str, ...]
    unsupported_models: tuple[str, ...]
    component_statuses: tuple[WarmupComponentStatus, ...]
    provider_info: ProviderInfo
    ready: bool


ONNX_WARMUP_HANDLERS = {
    FORMULA_DETECTOR_ID: warmup_formula_detector,
    FORMULA_RECOGNIZER_ID: warmup_formula_recognizer,
    TEXT_DETECTOR_ID: warmup_text_detector,
    TEXT_RECOGNIZER_ID: warmup_pp_text_recognizer,
    EN_TEXT_DETECTOR_ID: warmup_text_detector,
    EN_TEXT_RECOGNIZER_ID: warmup_pp_text_recognizer,
}


class MathCraftRuntime:
    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        provider_preference: str = "auto",
        manifest: Manifest | None = None,
    ) -> None:
        self.cache_dir = resolve_cache_dir(cache_dir)
        self.provider_preference = provider_preference
        self.manifest = manifest or load_manifest()

    def check_models(self, include_optional: bool = True):
        return inspect_manifest_cache(
            self.cache_dir, self.manifest, include_optional=include_optional
        )

    def _resolve_model_dir(self, model_id: str) -> Path:
        states = self.check_models()
        return states[model_id].model_dir

    def get_runtime_info(self) -> DoctorReport:
        return run_doctor(
            cache_dir=self.cache_dir,
            manifest=self.manifest,
            provider_preference=self.provider_preference,
        )

    def doctor(self) -> DoctorReport:
        return self.get_runtime_info()

    def download_models(
        self,
        *,
        model_ids: list[str] | tuple[str, ...] | None = None,
        source_overrides: dict[str, list[str] | tuple[str, ...]] | None = None,
        timeout: int = 60,
    ) -> list[Path]:
        selected = tuple(model_ids) if model_ids else tuple(self.manifest.models.keys())
        downloaded: list[Path] = []
        for model_id in selected:
            spec = self.manifest.models[model_id]
            downloaded.append(
                download_model_archive(
                    spec,
                    target_root=self.cache_dir,
                    timeout=timeout,
                    source_overrides=source_overrides,
                )
            )
        return downloaded

    def warmup(self, profile: str = "formula") -> WarmupPlan:
        profile_key = profile.strip().lower()
        if profile_key not in PROFILE_MODEL_IDS:
            raise ModelCacheError(f"unsupported warmup profile: {profile}")
        return self._warmup_selected_models(profile_key, PROFILE_MODEL_IDS[profile_key])

    def recognize_formula(
        self,
        image,
        *,
        max_new_tokens: int = 256,
    ) -> FormulaRecognitionResult:
        plan = self.warmup("formula")
        if not plan.ready:
            raise ModelCacheError(
                f"formula runtime is not ready: missing={plan.missing_models}, unsupported={plan.unsupported_models}"
            )
        rgb = load_image_rgb(image)
        text, score = recognize_formula_image(
            rgb,
            self._resolve_model_dir(FORMULA_RECOGNIZER_ID),
            plan.provider_info,
            max_new_tokens=max_new_tokens,
        )
        return FormulaRecognitionResult(
            text=text,
            score=score,
            provider=plan.provider_info.active_provider,
        )

    def recognize_mixed(
        self,
        image,
        *,
        min_text_score: float = 0.45,
        ocr_profile: str = "auto",
    ) -> MixedRecognitionResult:
        text_detector_id, text_recognizer_id, recognize_lines = self._select_mixed_text_models(
            ocr_profile
        )
        plan = self._warmup_selected_models(
            "mixed",
            (FORMULA_DETECTOR_ID, FORMULA_RECOGNIZER_ID, text_detector_id, text_recognizer_id),
        )
        if not plan.ready:
            raise ModelCacheError(
                f"mixed runtime is not ready: missing={plan.missing_models}, unsupported={plan.unsupported_models}"
            )
        rgb = load_image_rgb(image)
        bgr = rgb_to_bgr(rgb)
        formula_boxes = detect_formula_boxes(
            rgb,
            self._resolve_model_dir(FORMULA_DETECTOR_ID),
            plan.provider_info,
        )
        formula_block_boxes = tuple(item.box for item in formula_boxes)
        masked_bgr = rgb_to_bgr(mask_boxes(rgb, formula_block_boxes))

        detected_text_boxes, _scores = detect_text_boxes(
            bgr,
            self._resolve_model_dir(text_detector_id),
            plan.provider_info,
        )
        text_regions: list[OCRRegion] = []
        blocks: list[MathCraftBlock] = []
        text_segments = []
        for detected_box in detected_text_boxes:
            text_box = points_to_box(detected_box)
            text_segments.extend(
                split_text_box_around_formulas(text_box, formula_block_boxes)
            )
        if text_segments:
            crops = [
                get_rotate_crop_image(masked_bgr, box_to_points(segment.box))
                for segment in text_segments
            ]
            rec_results = recognize_lines(
                crops,
                self._resolve_model_dir(text_recognizer_id),
                plan.provider_info,
            )
            for segment, (text, score) in zip(text_segments, rec_results):
                cleaned_text = text.strip()
                if not cleaned_text or score < min_text_score:
                    continue
                region = OCRRegion(box=segment.box, text=cleaned_text, score=score)
                text_regions.append(region)
                blocks.append(
                    MathCraftBlock(
                        kind="text",
                        box=segment.box,
                        text=cleaned_text,
                        score=score,
                    )
                )
        for formula_box in formula_boxes:
            crop = get_rotate_crop_image(
                rgb,
                box_to_points(formula_box.box),
            )
            formula_text, formula_score = recognize_formula_image(
                crop,
                self._resolve_model_dir(FORMULA_RECOGNIZER_ID),
                plan.provider_info,
            )
            blocks.append(
                MathCraftBlock(
                    kind=formula_box.label,
                    box=formula_box.box,
                    text=formula_text,
                    score=min(formula_box.score, formula_score),
                )
            )
        if not blocks:
            formula = self.recognize_formula(rgb)
            blocks.append(
                MathCraftBlock(
                    kind="formula",
                    box=_full_image_box(rgb),
                    text=formula.text,
                    score=formula.score,
                )
            )
        ordered_blocks = tuple(
            block for line in group_blocks_into_lines(blocks) for block in line
        )
        regions = tuple(text_regions)
        merged = merge_blocks_text(ordered_blocks)
        return MixedRecognitionResult(
            text=merged,
            regions=regions,
            blocks=ordered_blocks,
            provider=plan.provider_info.active_provider,
        )

    def _warmup_selected_models(
        self,
        profile: str,
        model_ids: tuple[str, ...],
    ) -> WarmupPlan:
        report = self.get_runtime_info()
        missing: list[str] = []
        unsupported: list[str] = []
        component_statuses: list[WarmupComponentStatus] = []
        for model_id in model_ids:
            state = report.cache_states[model_id]
            spec = self.manifest.models[model_id]
            if not state.complete:
                missing.append(model_id)
                continue
            if spec.runtime != "onnx":
                unsupported.append(model_id)
                component_statuses.append(
                    WarmupComponentStatus(
                        model_id=model_id,
                        ready=False,
                        detail=f"runtime '{spec.runtime}' is not supported in MathCraft ONNX v1",
                    )
                )
                continue
            handler = ONNX_WARMUP_HANDLERS.get(model_id)
            if handler is None:
                unsupported.append(model_id)
                component_statuses.append(
                    WarmupComponentStatus(
                        model_id=model_id,
                        ready=False,
                        detail="no ONNX warmup handler registered",
                    )
                )
                continue
            try:
                handler(state.model_dir, report.provider_info)
                component_statuses.append(
                    WarmupComponentStatus(model_id=model_id, ready=True, detail="ok")
                )
            except Exception as exc:
                component_statuses.append(
                    WarmupComponentStatus(model_id=model_id, ready=False, detail=str(exc))
                )
        return WarmupPlan(
            profile=profile,
            required_models=model_ids,
            missing_models=tuple(missing),
            unsupported_models=tuple(unsupported),
            component_statuses=tuple(component_statuses),
            provider_info=report.provider_info,
            ready=not missing
            and not unsupported
            and all(item.ready for item in component_statuses),
        )

    def _select_mixed_text_models(self, ocr_profile: str):
        profile = (ocr_profile or "auto").strip().lower()
        if profile not in {"auto", "en", "ch"}:
            raise ModelCacheError(f"unsupported mixed OCR profile: {ocr_profile}")
        states = self.check_models()
        if profile in {"auto", "ch"} and (
            states.get(TEXT_DETECTOR_ID) is not None
            and states[TEXT_DETECTOR_ID].complete
            and states.get(TEXT_RECOGNIZER_ID) is not None
            and states[TEXT_RECOGNIZER_ID].complete
        ):
            return TEXT_DETECTOR_ID, TEXT_RECOGNIZER_ID, recognize_pp_text_lines
        if profile == "ch":
            raise ModelCacheError("Chinese mixed OCR profile is not ready")
        if (
            profile in {"auto", "en"}
            and states.get(EN_TEXT_DETECTOR_ID) is not None
            and states[EN_TEXT_DETECTOR_ID].complete
            and states.get(EN_TEXT_RECOGNIZER_ID) is not None
            and states[EN_TEXT_RECOGNIZER_ID].complete
        ):
            return EN_TEXT_DETECTOR_ID, EN_TEXT_RECOGNIZER_ID, recognize_pp_text_lines
        if profile == "en":
            raise ModelCacheError("English mixed OCR profile is not ready")
        raise ModelCacheError("No mixed OCR profile is ready")


def _full_image_box(image) -> Box4P:
    height, width = image.shape[:2]
    return ((0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height)))
