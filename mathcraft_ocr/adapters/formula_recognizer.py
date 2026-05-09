# coding: utf-8

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from .common import create_session


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


def _count_latex_tokens(text: str) -> int:
    """统计 LaTeX 公式中的语义单元数量。

    一个语义单元可以是：
    - LaTeX 命令（\\foo、\\bar12 等）
    - 单个字母或数字
    - 数学运算符（+ - = < > 等）
    - 希腊字母（作为整体）

    空格、花括号、下划线、上标等结构性符号不计入，
    但它们的存在暗示有内容——若结构性符号充足也计为有效。
    """
    import re

    count = 0
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if ch == "\\":
            # LaTeX 命令：\ 后跟字母序列（可选空格/非字母终止）
            j = i + 1
            while j < n and (text[j].isalpha() or text[j] == "@"):
                j += 1
            cmd = text[i:j]
            if len(cmd) >= 2:
                count += 1
            i = j
        elif ch.isalpha() or ch.isdigit():
            count += 1
            i += 1
        elif ch in "+-=*/<>|!?′∞∂∇∫∏∑√∝±×÷·∘∧∨∩∪⊂⊃∈∉⊆⊇≤≥≠≈≡≅∼∝⊥∥∠△□◇∇∀∃∄∅ℕℤℚℝℂℍ":
            count += 1
            i += 1
        else:
            i += 1

    # 如果没有任何字母/数字/命令，但有足够的 LaTeX 结构标记（{}_^$&），
    # 也算作有内容（例如纯符号公式）
    if count == 0:
        structural = sum(1 for ch in text if ch in "{}_^$&#")
        if structural >= 4:
            count = 1

    return count


@lru_cache(maxsize=8)
def _load_processor(model_dir: str):
    _disable_transformers_framework_imports()
    _disable_transformers_torchvision_probe()
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
    return recognize_formula_images(
        [image],
        model_dir,
        provider_info,
        max_new_tokens=max_new_tokens,
    )[0]


def recognize_formula_images(
    images: list[Image.Image | np.ndarray],
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

    pil_images = [image if isinstance(image, Image.Image) else Image.fromarray(image) for image in images]
    features = processor(images=pil_images, return_tensors="np")
    pixel_values = np.asarray(features["pixel_values"], dtype=np.float32)

    encoder_input_name = encoder_session.get_inputs()[0].name
    encoder_hidden_states = encoder_session.run(
        None,
        {encoder_input_name: pixel_values},
    )[0]

    tokenizer = processor.tokenizer
    decoder_start_id, eos_id = _load_generation_ids(root, tokenizer)
    batch_size = len(pil_images)
    input_ids = np.full((batch_size, 1), decoder_start_id, dtype=np.int64)
    token_ids: list[list[int]] = [[] for _ in range(batch_size)]
    token_scores: list[list[float]] = [[] for _ in range(batch_size)]
    finished = np.zeros((batch_size,), dtype=bool)
    pad_after_finish_id = eos_id if eos_id is not None else decoder_start_id

    for _ in range(max_new_tokens):
        decoder_inputs = {
            decoder_session.get_inputs()[0].name: input_ids,
            decoder_session.get_inputs()[1].name: encoder_hidden_states,
        }
        logits = decoder_session.run(None, decoder_inputs)[0]
        step_logits = logits[:, -1, :]
        step_probs = _softmax(step_logits)
        next_tokens = np.argmax(step_probs, axis=1).astype(np.int64)
        next_column = next_tokens.copy()
        for row, next_token in enumerate(next_tokens.tolist()):
            if finished[row]:
                next_column[row] = pad_after_finish_id
                continue
            next_prob = float(step_probs[row, next_token])
            if eos_id is not None and next_token == eos_id:
                finished[row] = True
                next_column[row] = pad_after_finish_id
                continue
            token_ids[row].append(int(next_token))
            token_scores[row].append(next_prob)
        if bool(np.all(finished)):
            break
        input_ids = np.concatenate(
            [input_ids, next_column.reshape(batch_size, 1)],
            axis=1,
        )

    results: list[tuple[str, float]] = []
    for ids, scores in zip(token_ids, token_scores):
        text = tokenizer.decode(ids, skip_special_tokens=True).strip()
        score = float(sum(scores) / len(scores)) if scores else 0.0
        # 输出质量检测：降低低质量/幻觉输出的分数
        quality = _check_output_quality(text, ids)
        if quality.low_quality:
            score = min(score, quality.adjusted_score)
        results.append((text, score))
    return results


def _check_output_quality(text: str, token_ids: list[int]) -> "_OutputQuality":
    """检测公式识别输出质量，识别幻觉/重复模式。"""
    # 1) 空输出
    if not text.strip():
        return _OutputQuality(True, 0.0, "empty")

    # 2) 过短：统计 LaTeX 语义单元（命令、字母、数字、数学符号）
    meaningful = _count_latex_tokens(text)
    if meaningful < 2:
        return _OutputQuality(True, 0.15, "too_short")

    # 3) 检测连续重复 token（同一 token 连续出现超过阈值）
    if token_ids:
        max_consecutive = _max_consecutive_same(token_ids)
        if max_consecutive >= 8:
            return _OutputQuality(True, 0.1, f"repeated_token_x{max_consecutive}")

    # 4) 检测 token n-gram 重复（多 token 序列循环出现，如 \chi_{\pm} 重复）
    if token_ids and len(token_ids) >= 12:
        ngram_repeat = _detect_token_ngram_repeat(token_ids)
        if ngram_repeat:
            return _OutputQuality(True, 0.1, f"ngram_repeat_{ngram_repeat}")

    # 5) 检测循环模式（任意位置出现的重复子串）
    if text:
        cycle_ratio = _detect_cycle(text, min_cycle=6, max_cycle=40)
        if cycle_ratio > 0.5:
            return _OutputQuality(True, 0.15, f"cycle_ratio_{cycle_ratio:.2f}")

    # 6) 过长的单 token 重复序列（例如 \chi_{\pm} 重复 >10 次）
    tokens = text.split()
    if len(tokens) > 10:
        from collections import Counter
        freq = Counter(tokens)
        if freq:
            top_count = freq.most_common(1)[0][1]
            if top_count > 8 and top_count / len(tokens) > 0.5:
                return _OutputQuality(True, 0.12, f"token_dominated_{freq.most_common(1)[0][0]}")

    return _OutputQuality(False, 1.0, "ok")


class _OutputQuality:
    __slots__ = ("low_quality", "adjusted_score", "reason")

    def __init__(self, low_quality: bool, adjusted_score: float, reason: str):
        self.low_quality = low_quality
        self.adjusted_score = adjusted_score
        self.reason = reason


def _max_consecutive_same(ids: list[int]) -> int:
    """返回连续相同 token 的最大长度。"""
    if not ids:
        return 0
    max_run = 1
    current_run = 1
    for i in range(1, len(ids)):
        if ids[i] == ids[i - 1]:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 1
    return max_run


def _detect_token_ngram_repeat(
    ids: list[int],
    min_ngram: int = 3,
    max_ngram: int = 8,
    min_repeats: int = 5,
) -> str | None:
    """检测 token ID 序列中的 n-gram 循环重复。

    对于 ``\\chi _ { \\pm }`` 这种由多个不同 token 组成的重复单元，
    普通连续相同检测无法捕获，但 n-gram 检测可以发现循环模式。

    返回描述字符串（如 "len4_x12"），或 None 表示未检测到。
    """
    n = len(ids)
    if n < min_ngram * min_repeats:
        return None

    # 使用后缀数组思路：对于每个起始位置，尝试不同长度的 n-gram
    for ngram_len in range(min_ngram, min(max_ngram + 1, n // min_repeats + 1)):
        ngram = tuple(ids[:ngram_len])
        count = 1
        pos = ngram_len
        while pos + ngram_len <= n:
            if tuple(ids[pos:pos + ngram_len]) == ngram:
                count += 1
                pos += ngram_len
            else:
                pos += 1
        if count >= min_repeats and count * ngram_len >= n * 0.5:
            return f"len{ngram_len}_x{count}"

    # 也检查从非零位置开始的 n-gram（循环不一定从开头开始）
    for start in range(1, min(n // 4, 20)):
        for ngram_len in range(min_ngram, min(max_ngram + 1, (n - start) // min_repeats + 1)):
            ngram = tuple(ids[start:start + ngram_len])
            count = 1
            pos = start + ngram_len
            while pos + ngram_len <= n:
                if tuple(ids[pos:pos + ngram_len]) == ngram:
                    count += 1
                    pos += ngram_len
                else:
                    pos += 1
            if count >= min_repeats and count * ngram_len >= (n - start) * 0.5:
                return f"len{ngram_len}_x{count}_offset{start}"

    return None


def _detect_cycle(text: str, min_cycle: int = 4, max_cycle: int = 30) -> float:
    """检测文本中任意位置的循环模式，返回被循环覆盖的字符比例。

    与旧版不同，此实现不限定循环必须从文本开头开始，
    而是搜索所有可能的子串作为候选模式。
    """
    n = len(text)
    if n < min_cycle * 2:
        return 0.0
    best_ratio = 0.0

    # 对每个可能的起始位置和循环长度进行检测
    max_start = min(n // 4, 50)  # 只检查前 50 个字符作为起始
    for start in range(0, max_start + 1):
        remaining = n - start
        for cycle_len in range(min_cycle, min(max_cycle, remaining // 2) + 1):
            pattern = text[start:start + cycle_len]
            matched = cycle_len  # 第一个模式自身
            pos = start + cycle_len
            while pos + cycle_len <= n:
                if text[pos:pos + cycle_len] == pattern:
                    matched += cycle_len
                    pos += cycle_len
                else:
                    pos += 1
            ratio = matched / remaining if remaining > 0 else 0.0
            if ratio > best_ratio:
                best_ratio = ratio
                if best_ratio > 0.7:
                    return best_ratio

    return best_ratio
