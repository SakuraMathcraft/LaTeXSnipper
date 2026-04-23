# coding: utf-8

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from .common import create_session


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=-1, keepdims=True)


@lru_cache(maxsize=8)
def _load_processor(model_dir: str):
    from transformers import AutoTokenizer, TrOCRProcessor, ViTImageProcessor

    image_processor = ViTImageProcessor.from_pretrained(model_dir, use_fast=False)
    tokenizer = AutoTokenizer.from_pretrained(model_dir, use_fast=True)
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
            decoder_start_id = decoder_config.get("decoder_start_token_id", decoder_start_id)
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
    root = Path(model_dir)
    processor = _load_processor(str(root))
    encoder_session = create_session(root / "encoder_model.onnx", provider_info)
    decoder_session = create_session(root / "decoder_model.onnx", provider_info)

    pil_image = image if isinstance(image, Image.Image) else Image.fromarray(image)
    features = processor(images=pil_image, return_tensors="np")
    pixel_values = np.asarray(features["pixel_values"], dtype=np.float32)

    encoder_input_name = encoder_session.get_inputs()[0].name
    encoder_hidden_states = encoder_session.run(
        None,
        {encoder_input_name: pixel_values},
    )[0]

    tokenizer = processor.tokenizer
    decoder_start_id, eos_id = _load_generation_ids(root, tokenizer)
    input_ids = np.asarray([[decoder_start_id]], dtype=np.int64)
    token_ids: list[int] = []
    token_scores: list[float] = []

    for _ in range(max_new_tokens):
        decoder_inputs = {
            decoder_session.get_inputs()[0].name: input_ids,
            decoder_session.get_inputs()[1].name: encoder_hidden_states,
        }
        logits = decoder_session.run(None, decoder_inputs)[0]
        step_logits = logits[:, -1, :]
        step_probs = _softmax(step_logits)
        next_token = int(np.argmax(step_probs[0]))
        next_prob = float(step_probs[0, next_token])
        if eos_id is not None and next_token == eos_id:
            break
        token_ids.append(next_token)
        token_scores.append(next_prob)
        input_ids = np.concatenate(
            [input_ids, np.asarray([[next_token]], dtype=np.int64)],
            axis=1,
        )

    text = tokenizer.decode(token_ids, skip_special_tokens=True).strip()
    score = float(sum(token_scores) / len(token_scores)) if token_scores else 0.0
    return text, score
