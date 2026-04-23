# coding: utf-8

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from rapidocr import EngineType, LangRec, ModelType, OCRVersion
from rapidocr.ch_ppocr_rec import TextRecInput, TextRecognizer
from rapidocr.utils.typings import TaskType


class _Config(dict):
    def __init__(self, *args, **kwargs):
        super().__init__()
        data = dict(*args, **kwargs)
        for key, value in data.items():
            if isinstance(value, dict):
                value = _Config(value)
            self[key] = value

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def warmup_pp_text_recognizer(model_dir: str | Path, provider_info) -> None:
    recognizer = _create_pp_text_recognizer(Path(model_dir), provider_info)
    recognizer.rec_batch_num = 1


def recognize_pp_text_lines(
    images_bgr: list[np.ndarray],
    model_dir: str | Path,
    provider_info,
) -> list[tuple[str, float]]:
    if not images_bgr:
        return []
    recognizer = _create_pp_text_recognizer(Path(model_dir), provider_info)
    recognizer.rec_batch_num = min(max(len(images_bgr), 1), 6)
    rec_input = TextRecInput(img=images_bgr, return_word_box=False)
    output = recognizer(rec_input)
    return [(str(text), float(score)) for text, score in zip(output.txts, output.scores)]


def _create_pp_text_recognizer(model_dir: Path, provider_info) -> TextRecognizer:
    model_dir = model_dir.resolve()
    use_cuda = bool(getattr(provider_info, "device", "") == "gpu")
    return _create_pp_text_recognizer_cached(str(model_dir), use_cuda)


@lru_cache(maxsize=8)
def _create_pp_text_recognizer_cached(model_dir: str, use_cuda: bool) -> TextRecognizer:
    model_dir = Path(model_dir)
    model_candidates = sorted(model_dir.glob("**/*rec*.onnx"))
    if not model_candidates:
        raise FileNotFoundError(f"no PP-OCR recognizer onnx file found under {model_dir}")
    model_path = model_candidates[0]
    dict_path = _find_pp_vocab(model_dir)
    if dict_path is None:
        raise FileNotFoundError(f"missing PP-OCR vocabulary under {model_dir}")
    model_name = model_path.name
    is_server = "server" in model_name or "server" in model_dir.name
    is_v5 = "v5" in model_name or "v5" in model_dir.name
    is_english = dict_path.name == "en_dict.txt"
    config = _Config({
        "engine_type": EngineType.ONNXRUNTIME,
        "lang_type": LangRec.EN if is_english else LangRec.CH,
        "model_type": ModelType.SERVER if is_server else ModelType.MOBILE,
        "ocr_version": OCRVersion.PPOCRV5 if is_v5 else OCRVersion.PPOCRV4,
        "task_type": TaskType.REC,
        "model_path": str(model_path),
        "model_dir": None,
        "rec_keys_path": str(dict_path),
        "rec_img_shape": [3, 48, 320],
        "rec_batch_num": 6,
        "font_path": None,
        "engine_cfg": {
            "intra_op_num_threads": -1,
            "inter_op_num_threads": -1,
            "enable_cpu_mem_arena": False,
            "cpu_ep_cfg": {"arena_extend_strategy": "kSameAsRequested"},
            "use_cuda": use_cuda,
            "cuda_ep_cfg": {
                "device_id": 0,
                "arena_extend_strategy": "kNextPowerOfTwo",
                "cudnn_conv_algo_search": "EXHAUSTIVE",
                "do_copy_in_default_stream": True,
            },
            "use_dml": False,
            "dm_ep_cfg": None,
            "use_cann": False,
            "cann_ep_cfg": {
                "device_id": 0,
                "arena_extend_strategy": "kNextPowerOfTwo",
                "npu_mem_limit": 21474836480,
                "op_select_impl_mode": "high_performance",
                "optypelist_for_implmode": "Gelu",
                "enable_cann_graph": True,
            },
        },
    })
    return TextRecognizer(config)


def clear_text_recognizer_cache() -> None:
    _create_pp_text_recognizer_cached.cache_clear()


def _find_pp_vocab(model_dir: Path) -> Path | None:
    for name in ("en_dict.txt", "ppocr_keys_v1.txt"):
        candidate = model_dir / name
        if candidate.is_file():
            return candidate
    return None
