# coding: utf-8

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rapidocr.utils.process_img import get_rotate_crop_image

from .adapters.formula_detector import detect_formula_boxes, warmup_formula_detector
from .adapters.formula_recognizer import (
    recognize_formula_image,
    recognize_formula_images,
    warmup_formula_recognizer,
)
from .adapters.text_detector import detect_text_boxes, warmup_text_detector
from .adapters.text_recognizer import (
    recognize_pp_text_lines,
    warmup_pp_text_recognizer,
)
from .cache import inspect_manifest_roots, resolve_model_roots, resolve_user_models_dir
from .doctor import DoctorReport, run_doctor
from .downloader import download_model_archive
from .errors import ModelCacheError
from .hardware import choose_rec_batch_num, detect_hardware_info
from .image import load_image_rgb, rgb_to_bgr
from .layout import (
    annotate_blocks,
    box_to_points,
    is_informative_ocr_box,
    mask_boxes,
    merge_blocks_text,
    points_to_box,
    resolve_formula_text_conflicts,
    split_text_box_around_formulas,
)
from .manifest import Manifest, load_manifest
from .providers import ProviderInfo
from .results import Box4P, FormulaRecognitionResult, MathCraftBlock, MixedRecognitionResult, OCRRegion


FORMULA_DETECTOR_ID = "mathcraft-formula-det"
FORMULA_RECOGNIZER_ID = "mathcraft-formula-rec"
TEXT_DETECTOR_ID = "mathcraft-text-det"
TEXT_RECOGNIZER_ID = "mathcraft-text-rec"

PROFILE_MODEL_IDS = {
    "formula": (FORMULA_DETECTOR_ID, FORMULA_RECOGNIZER_ID),
    "text": (TEXT_DETECTOR_ID, TEXT_RECOGNIZER_ID),
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
}


class MathCraftRuntime:
    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        provider_preference: str = "auto",
        manifest: Manifest | None = None,
        bundled_models_dir: str | Path | None = None,
    ) -> None:
        self.cache_dir = resolve_user_models_dir(cache_dir)
        self.bundled_models_dir = Path(bundled_models_dir) if bundled_models_dir else None
        self.model_roots = resolve_model_roots(cache_dir, bundled_models_dir)
        self.provider_preference = provider_preference
        self.manifest = manifest or load_manifest()
        self._warmup_cache: dict[str, WarmupPlan] = {}
        self._rec_batch_cache: dict[str, int] = {}

    def check_models(self, include_optional: bool = True):
        return inspect_manifest_roots(
            self.model_roots, self.manifest, include_optional=include_optional
        )

    def _resolve_model_dir(self, model_id: str) -> Path:
        states = self.check_models()
        return states[model_id].model_dir

    def get_runtime_info(self) -> DoctorReport:
        return run_doctor(
            cache_dir=self.cache_dir,
            bundled_models_dir=self.bundled_models_dir,
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
        self.clear_warmup_cache()
        return downloaded

    def clear_warmup_cache(self) -> None:
        self._warmup_cache.clear()

    def warmup(self, profile: str = "formula") -> WarmupPlan:
        profile_key = profile.strip().lower()
        if profile_key == "formula":
            model_ids = PROFILE_MODEL_IDS["formula"]
        elif profile_key == "text":
            model_ids = PROFILE_MODEL_IDS["text"]
        elif profile_key == "mixed":
            model_ids = PROFILE_MODEL_IDS["mixed"]
        else:
            raise ModelCacheError(f"unsupported warmup profile: {profile}")
        return self._warmup_selected_models(profile_key, model_ids)

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

    def recognize_text(
        self,
        image,
        *,
        min_text_score: float = 0.45,
    ) -> MixedRecognitionResult:
        plan = self._warmup_selected_models("text", PROFILE_MODEL_IDS["text"])
        if not plan.ready:
            raise ModelCacheError(
                f"text runtime is not ready: missing={plan.missing_models}, unsupported={plan.unsupported_models}"
            )
        rgb = load_image_rgb(image)
        bgr = rgb_to_bgr(rgb)
        detected_text_boxes, _scores = detect_text_boxes(
            bgr,
            self._resolve_model_dir(TEXT_DETECTOR_ID),
            plan.provider_info,
        )
        regions: list[OCRRegion] = []
        blocks: list[MathCraftBlock] = []
        text_candidates = [
            (detected_box, points_to_box(detected_box))
            for detected_box in detected_text_boxes
            if is_informative_ocr_box(bgr, points_to_box(detected_box))
        ]
        if text_candidates:
            crops = [
                get_rotate_crop_image(bgr, box_to_points(box))
                for _detected_box, box in text_candidates
            ]
            rec_results = recognize_pp_text_lines(
                crops,
                self._resolve_model_dir(TEXT_RECOGNIZER_ID),
                plan.provider_info,
                rec_batch_num=self._rec_batch_num(plan.provider_info),
            )
            for (_detected_box, box), (text, score) in zip(text_candidates, rec_results):
                cleaned_text = text.strip()
                if not cleaned_text or score < min_text_score:
                    continue
                regions.append(OCRRegion(box=box, text=cleaned_text, score=score))
                blocks.append(
                    MathCraftBlock(
                        kind="text",
                        box=box,
                        text=cleaned_text,
                        score=score,
                        source="text_rec",
                    )
                )
        height, width = rgb.shape[:2]
        ordered_blocks = annotate_blocks(blocks, image_size=(int(width), int(height)))
        return MixedRecognitionResult(
            text=merge_blocks_text(ordered_blocks),
            regions=tuple(regions),
            blocks=ordered_blocks,
            provider=plan.provider_info.active_provider,
        )

    def recognize_mixed(
        self,
        image,
        *,
        min_text_score: float = 0.45,
    ) -> MixedRecognitionResult:
        plan = self._warmup_selected_models(
            "mixed",
            PROFILE_MODEL_IDS["mixed"],
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
        formula_boxes = tuple(
            formula_box
            for formula_box in formula_boxes
            if is_informative_ocr_box(
                rgb,
                formula_box.box,
                min_width=4.0,
                min_height=4.0,
                min_area=24.0,
                blank_mean_threshold=252.0,
                blank_std_threshold=3.0,
            )
        )
        height, width = rgb.shape[:2]
        formula_block_boxes = tuple(item.box for item in formula_boxes)
        masked_bgr = rgb_to_bgr(
            mask_boxes(rgb, formula_block_boxes, margin=_formula_mask_margin(width, height))
        )

        detected_text_boxes, _scores = detect_text_boxes(
            bgr,
            self._resolve_model_dir(TEXT_DETECTOR_ID),
            plan.provider_info,
        )
        text_regions: list[OCRRegion] = []
        blocks: list[MathCraftBlock] = []
        text_segments = []
        for detected_box in detected_text_boxes:
            text_box = points_to_box(detected_box)
            if not is_informative_ocr_box(bgr, text_box):
                continue
            text_segments.extend(
                segment
                for segment in split_text_box_around_formulas(text_box, formula_block_boxes)
                if is_informative_ocr_box(masked_bgr, segment.box)
            )
        if text_segments:
            crops = [
                get_rotate_crop_image(masked_bgr, box_to_points(segment.box))
                for segment in text_segments
            ]
            rec_results = recognize_pp_text_lines(
                crops,
                self._resolve_model_dir(TEXT_RECOGNIZER_ID),
                plan.provider_info,
                rec_batch_num=self._rec_batch_num(plan.provider_info),
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
                        source="text_rec",
                    )
                )
        formula_crops = [
            get_rotate_crop_image(rgb, box_to_points(formula_box.box))
            for formula_box in formula_boxes
        ]
        formula_results = recognize_formula_images(
            formula_crops,
            self._resolve_model_dir(FORMULA_RECOGNIZER_ID),
            plan.provider_info,
        )
        for formula_box, (formula_text, formula_score) in zip(formula_boxes, formula_results):
            blocks.append(
                MathCraftBlock(
                    kind=formula_box.label,
                    box=formula_box.box,
                    text=formula_text,
                    score=min(formula_box.score, formula_score),
                    source="formula_rec",
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
                    source="formula_fallback",
                )
            )
        blocks = list(resolve_formula_text_conflicts(blocks, image_size=(int(width), int(height))))
        ordered_blocks = annotate_blocks(blocks, image_size=(int(width), int(height)))
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
        cached = self._warmup_cache.get(profile)
        if cached and cached.ready and cached.required_models == model_ids:
            return cached

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
        plan = WarmupPlan(
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
        if plan.ready:
            self._warmup_cache[profile] = plan
        return plan

    def _rec_batch_num(self, provider_info: ProviderInfo) -> int:
        key = "|".join(
            (
                str(provider_info.device or ""),
                str(provider_info.active_provider or ""),
                str(provider_info.gpu_runtime_ok),
            )
        )
        cached = self._rec_batch_cache.get(key)
        if cached:
            return cached
        batch = choose_rec_batch_num(provider_info, detect_hardware_info())
        self._rec_batch_cache[key] = batch
        return batch


def _full_image_box(image) -> Box4P:
    height, width = image.shape[:2]
    return ((0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height)))


def _formula_mask_margin(width: int, height: int) -> int:
    return max(2, int(round(max(width, height) / 640.0)))
