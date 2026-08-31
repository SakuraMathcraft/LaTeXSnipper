class ExternalModelError(RuntimeError):
    """Base error for external model calls."""

    def __init__(
        self,
        message: str,
        *,
        user_code: str = "external_model_error",
        user_context: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.user_code = user_code
        self.user_context = dict(user_context or {})


class ExternalModelConfigError(ExternalModelError):
    """Configuration is missing or invalid."""


class ExternalModelConnectionError(ExternalModelError):
    """Local API endpoint is unreachable."""


class ExternalModelResponseError(ExternalModelError):
    """Local API returned an unsupported payload."""
