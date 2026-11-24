from __future__ import annotations

import json
import os
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..hardware import choose_rec_batch_num, detect_hardware_info
from ..image import prepare_formula_image
from ..profiles import resolve_formula_variant
from ..providers import ProviderInfo
from .formula_inference import TokenDecoder, formula_decoder, load_formula_sessions


def _disable_transformers_framework_imports() -> None:
    os.environ["USE_TORCH"] = "0"
    os.environ["USE_TF"] = "0"
    os.environ["USE_FLAX"] = "0"
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")


def _disable_transformers_torchvision_probe() -> None:
    import transformers.utils.import_utils as import_utils

    import_utils._torchvision_available = False
    import_utils._torchvision_version = "0.0"


@lru_cache(maxsize=8)
def _load_processor(model_dir: str) -> Any:
    _disable_transformers_framework_imports()
    _disable_transformers_torchvision_probe()
    from transformers import AutoTokenizer, TrOCRProcessor, ViTImageProcessor

    # Model directories are local and their files are verified by the OCR runtime.
    image_processor = ViTImageProcessor.from_pretrained(  # nosec B615
        model_dir, use_fast=False, local_files_only=True
    )
    tokenizer = AutoTokenizer.from_pretrained(  # nosec B615
        model_dir, use_fast=True, local_files_only=True
    )
    return TrOCRProcessor(image_processor=image_processor, tokenizer=tokenizer)


def warmup_formula_recognizer(
    model_dir: str | Path, provider_info: ProviderInfo, *, model_variant: str = "auto"
) -> None:
    variant = resolve_formula_variant(provider_info.active_provider, model_variant)
    load_formula_sessions(Path(model_dir), provider_info, variant)


def _load_generation_ids(model_dir: Path, tokenizer) -> tuple[int, int | None]:
    decoder_start_id = None
    eos_id = None
    for filename in ("generation_config.json", "config.json"):
        path = model_dir / filename
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        decoder_start_id = data.get("decoder_start_token_id", decoder_start_id)
        eos_id = data.get("eos_token_id", eos_id)
        decoder_config = data.get("decoder")
        if isinstance(decoder_config, dict):
            decoder_start_id = decoder_config.get(
                "decoder_start_token_id", decoder_start_id
            )
            eos_id = decoder_config.get("eos_token_id", eos_id)
        if decoder_start_id is not None and eos_id is not None:
            break
    if decoder_start_id is None:
        decoder_start_id = tokenizer.bos_token_id
    if decoder_start_id is None:
        raise ValueError(f"missing decoder_start_token_id under {model_dir}")
    if eos_id is None:
        eos_id = tokenizer.eos_token_id
    return int(decoder_start_id), int(eos_id) if eos_id is not None else None


def recognize_formula_image(
    image: Image.Image | np.ndarray,
    model_dir: str | Path,
    provider_info: ProviderInfo,
    *,
    max_new_tokens: int = 256,
    model_variant: str = "auto",
) -> tuple[str, float]:
    return recognize_formula_images(
        [image],
        model_dir,
        provider_info,
        max_new_tokens=max_new_tokens,
        model_variant=model_variant,
    )[0]


def recognize_formula_images(
    images: Sequence[Image.Image | np.ndarray],
    model_dir: str | Path,
    provider_info: ProviderInfo,
    *,
    max_new_tokens: int = 256,
    model_variant: str = "auto",
) -> list[tuple[str, float]]:
    if not images:
        return []
    root = Path(model_dir)
    processor = _load_processor(str(root))
    variant = resolve_formula_variant(provider_info.active_provider, model_variant)
    sessions = load_formula_sessions(root, provider_info, variant)
    tokenizer = processor.tokenizer
    decoder_start_id, eos_id = _load_generation_ids(root, tokenizer)
    batch_size = (
        choose_rec_batch_num(provider_info, detect_hardware_info(provider_info))
        if len(images) > 1
        else 1
    )
    results: list[tuple[str, float]] = []
    for start in range(0, len(images), batch_size):
        batch = images[start : start + batch_size]
        features = processor(
            images=[prepare_formula_image(image) for image in batch],
            return_tensors="np",
        )
        decoder = formula_decoder(
            sessions, np.asarray(features["pixel_values"]), provider_info, variant
        )
        token_ids, token_scores, stopped_for_repetition = _generate_formula_tokens(
            decoder,
            batch_size=len(batch),
            decoder_start_id=decoder_start_id,
            eos_id=eos_id,
            max_new_tokens=min(max_new_tokens, 512),
        )

        for row, (ids, scores) in enumerate(zip(token_ids, token_scores, strict=True)):
            text = tokenizer.decode(ids, skip_special_tokens=True).strip()
            score = float(sum(scores) / len(scores)) if scores else 0.0
            if stopped_for_repetition[row]:
                score = min(score, 0.5)
            results.append((text, score))
        del decoder
    return results


def _generate_formula_tokens(
    decoder: TokenDecoder,
    *,
    batch_size: int,
    decoder_start_id: int,
    eos_id: int | None,
    max_new_tokens: int,
) -> tuple[list[list[int]], list[list[float]], np.ndarray]:
    active_indices = np.arange(batch_size, dtype=np.int64)
    input_ids = np.full((batch_size, 1), decoder_start_id, dtype=np.int64)
    finished = np.zeros(batch_size, dtype=bool)
    token_ids: list[list[int]] = [[] for _ in range(batch_size)]
    token_scores: list[list[float]] = [[] for _ in range(batch_size)]
    stopped_for_repetition = np.zeros((batch_size,), dtype=bool)
    for position in range(max_new_tokens):
        next_tokens, confidence = decoder.step(input_ids, position)
        for row, next_token in enumerate(next_tokens.tolist()):
            result_row = int(active_indices[row])
            if finished[result_row]:
                continue
            if eos_id is not None and next_token == eos_id:
                finished[result_row] = True
                continue
            token_ids[result_row].append(int(next_token))
            token_scores[result_row].append(float(confidence[row]))
            repeated_suffix_start = _repeated_token_suffix_start(token_ids[result_row])
            if repeated_suffix_start is not None:
                del token_ids[result_row][repeated_suffix_start:]
                del token_scores[result_row][repeated_suffix_start:]
                stopped_for_repetition[result_row] = True
                finished[result_row] = True
        if finished.all():
            break
        active_finished = finished[active_indices]
        if active_finished.any():
            keep = np.flatnonzero(~active_finished)
            if decoder.compact(keep):
                active_indices = active_indices[keep]
                input_ids = next_tokens[keep, None]
                continue
        input_ids[:, 0] = next_tokens

    return token_ids, token_scores, stopped_for_repetition


def _repeated_token_suffix_start(
    token_ids: list[int],
    *,
    min_generated_tokens: int = 64,
    min_repeated_tokens: int = 32,
    max_period: int = 4,
    min_repetitions: int = 8,
) -> int | None:
    token_count = len(token_ids)
    if token_count < min_generated_tokens:
        return None
    for period in range(1, max_period + 1):
        pattern = token_ids[-period:]
        start = token_count - period
        repetitions = 1
        while start >= period and token_ids[start - period : start] == pattern:
            start -= period
            repetitions += 1
        if repetitions < min_repetitions or repetitions * period < min_repeated_tokens:
            continue
        return start + period
    return None
