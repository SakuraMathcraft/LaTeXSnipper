from __future__ import annotations

import json
import os
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .common import create_session
from .formula_inference import FormulaDecoder, encode_formula


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


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=-1, keepdims=True)


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


def warmup_formula_recognizer(model_dir: str | Path, provider_info) -> None:
    root = Path(model_dir)
    encoder = root / "encoder_model.onnx"
    decoder = root / "decoder_model.onnx"
    if not encoder.is_file():
        raise FileNotFoundError(f"missing encoder model under {root}")
    if not decoder.is_file():
        raise FileNotFoundError(f"missing decoder model under {root}")
    create_session(encoder, provider_info)
    create_session(decoder, provider_info)


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
    provider_info,
    *,
    max_new_tokens: int = 256,
) -> tuple[str, float]:
    return recognize_formula_images(
        [image],
        model_dir,
        provider_info,
        max_new_tokens=max_new_tokens,
    )[0]


def recognize_formula_images(
    images: Sequence[Image.Image | np.ndarray],
    model_dir: str | Path,
    provider_info,
    *,
    max_new_tokens: int = 256,
) -> list[tuple[str, float]]:
    if not images:
        return []
    root = Path(model_dir)
    processor = _load_processor(str(root))
    encoder_session = create_session(root / "encoder_model.onnx", provider_info)
    decoder_session = create_session(root / "decoder_model.onnx", provider_info)

    pil_images = [
        image if isinstance(image, Image.Image) else Image.fromarray(image)
        for image in images
    ]
    features = processor(images=pil_images, return_tensors="np")
    pixel_values = np.asarray(features["pixel_values"], dtype=np.float32)

    cuda_device_id = (
        int(provider_info.device_id or 0)
        if provider_info.active_provider == "CUDAExecutionProvider"
        else None
    )
    encoder_hidden_states = encode_formula(
        encoder_session, pixel_values, cuda_device_id
    )

    tokenizer = processor.tokenizer
    decoder_start_id, eos_id = _load_generation_ids(root, tokenizer)
    token_ids, token_scores, stopped_for_repetition = _generate_formula_tokens(
        decoder_session,
        encoder_hidden_states,
        decoder_start_id=decoder_start_id,
        eos_id=eos_id,
        max_new_tokens=max_new_tokens,
        cuda_device_id=cuda_device_id,
    )

    results: list[tuple[str, float]] = []
    for row, (ids, scores) in enumerate(zip(token_ids, token_scores, strict=False)):
        text = tokenizer.decode(ids, skip_special_tokens=True).strip()
        score = float(sum(scores) / len(scores)) if scores else 0.0
        if stopped_for_repetition[row]:
            score = min(score, 0.5)
        results.append((text, score))
    return results


def _generate_formula_tokens(
    decoder_session,
    encoder_hidden_states,
    *,
    decoder_start_id: int,
    eos_id: int | None,
    max_new_tokens: int,
    cuda_device_id: int | None = None,
) -> tuple[list[list[int]], list[list[float]], np.ndarray]:
    decoder = FormulaDecoder(decoder_session, encoder_hidden_states, cuda_device_id)
    batch_size = decoder.batch_size
    active_indices = np.arange(batch_size, dtype=np.int64)
    active_input_ids = np.full((batch_size, 1), decoder_start_id, dtype=np.int64)
    token_ids: list[list[int]] = [[] for _ in range(batch_size)]
    token_scores: list[list[float]] = [[] for _ in range(batch_size)]
    stopped_for_repetition = np.zeros((batch_size,), dtype=bool)
    for _ in range(max_new_tokens):
        step_logits = decoder.step(active_input_ids)
        step_probs = _softmax(step_logits)
        next_tokens = np.argmax(step_probs, axis=1).astype(np.int64)
        keep_active_rows: list[int] = []
        for active_row, next_token in enumerate(next_tokens.tolist()):
            result_row = int(active_indices[active_row])
            if eos_id is not None and next_token == eos_id:
                continue
            token_ids[result_row].append(int(next_token))
            token_scores[result_row].append(float(step_probs[active_row, next_token]))
            repeated_suffix_start = _repeated_token_suffix_start(token_ids[result_row])
            if repeated_suffix_start is not None:
                del token_ids[result_row][repeated_suffix_start:]
                del token_scores[result_row][repeated_suffix_start:]
                stopped_for_repetition[result_row] = True
                continue
            keep_active_rows.append(active_row)
        if not keep_active_rows:
            break
        active_input_ids = np.concatenate(
            [
                active_input_ids[keep_active_rows],
                next_tokens[keep_active_rows].reshape(len(keep_active_rows), 1),
            ],
            axis=1,
        )
        decoder.retain(keep_active_rows)
        active_indices = active_indices[keep_active_rows]

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
