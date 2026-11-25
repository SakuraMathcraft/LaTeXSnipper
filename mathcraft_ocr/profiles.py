from .errors import ProviderError

FORMULA_DETECTOR_ID = "mathcraft-formula-det"
FORMULA_RECOGNIZER_ID = "mathcraft-formula-rec"
TEXT_DETECTOR_ID = "mathcraft-text-det"
TEXT_RECOGNIZER_ID = "mathcraft-text-rec"
CPU_PROVIDER = "CPUExecutionProvider"
CUDA_PROVIDER = "CUDAExecutionProvider"
FORMULA_VARIANTS = {CPU_PROVIDER: "cpu-int8", CUDA_PROVIDER: "cuda-fp16"}
FP32_V2 = "fp32-v2"
FORMULA_VARIANT_CHOICES = ("auto", "fp32", FP32_V2, "cpu-int8", "cuda-fp16")
EDITION_PROVIDERS = {"cpu": CPU_PROVIDER, "gpu": CUDA_PROVIDER}
FORMULA_ROLES = frozenset({FORMULA_DETECTOR_ID, FORMULA_RECOGNIZER_ID})

PROFILE_MODEL_IDS = {
    "formula": (FORMULA_RECOGNIZER_ID,),
    "text": (TEXT_DETECTOR_ID, TEXT_RECOGNIZER_ID),
    "mixed": (
        FORMULA_DETECTOR_ID,
        FORMULA_RECOGNIZER_ID,
        TEXT_DETECTOR_ID,
        TEXT_RECOGNIZER_ID,
    ),
}


def resolve_formula_variant(provider: str | None, requested: str = "auto") -> str:
    optimized = FORMULA_VARIANTS.get(provider or "")
    if requested == "auto":
        return optimized or "fp32"
    if requested in ("fp32", FP32_V2) or requested == optimized:
        return requested
    raise ProviderError(
        f"Formula variant {requested} does not support Provider {provider}"
    )


def model_id_for_role(role: str, provider: str | None, requested: str = "auto") -> str:
    if role not in FORMULA_ROLES:
        return role
    variant = resolve_formula_variant(provider, requested)
    if variant == "fp32" or (variant == FP32_V2 and role == FORMULA_DETECTOR_ID):
        return role
    return f"{role}-{variant}"


def edition_model_ids(edition: str) -> tuple[str, ...]:
    return tuple(
        model_id_for_role(role, EDITION_PROVIDERS[edition])
        for role in PROFILE_MODEL_IDS["mixed"]
    )
