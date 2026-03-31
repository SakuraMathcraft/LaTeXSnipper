class ExternalModelError(RuntimeError):
    """Base error for external model calls."""


class ExternalModelConfigError(ExternalModelError):
    """Configuration is missing or invalid."""


class ExternalModelConnectionError(ExternalModelError):
    """Local API endpoint is unreachable."""


class ExternalModelResponseError(ExternalModelError):
    """Local API returned an unsupported payload."""
