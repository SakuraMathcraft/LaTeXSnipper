# coding: utf-8

from backend.model import ModelWrapper


def create_model_wrapper(default_model: str | None = None, auto_warmup: bool = True):
    print("[INFO] 内置识别运行时: MathCraft OCR")
    return ModelWrapper(default_model, auto_warmup=auto_warmup)
