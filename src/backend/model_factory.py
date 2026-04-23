# coding: utf-8

from backend.model import ModelWrapper


def create_model_wrapper(default_model: str | None = None, auto_warmup: bool = True):
    print("[INFO] model runtime: MathCraft local worker")
    return ModelWrapper(default_model, auto_warmup=auto_warmup)
