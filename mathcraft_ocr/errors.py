# coding: utf-8


class MathCraftError(RuntimeError):
    """Base error for MathCraft OCR."""


class ManifestError(MathCraftError):
    """Raised when the packaged model manifest is invalid."""


class ModelCacheError(MathCraftError):
    """Raised when model cache inspection or repair fails."""


class DownloadUnavailableError(MathCraftError):
    """Raised when no usable model source is available."""


class ProviderError(MathCraftError):
    """Raised when ONNX runtime/provider detection fails."""
