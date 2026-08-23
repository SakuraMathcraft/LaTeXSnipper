"""Versioned Automation API for local and authorized remote clients."""

from .auth import AutomationApiAuth, AuthenticatedPrincipal


def __getattr__(name: str):
    if name in {"AutomationApiServer", "AutomationApiSettings", "AutomationApiSettingsError"}:
        from .server import AutomationApiServer, AutomationApiSettings, AutomationApiSettingsError

        return {
            "AutomationApiServer": AutomationApiServer,
            "AutomationApiSettings": AutomationApiSettings,
            "AutomationApiSettingsError": AutomationApiSettingsError,
        }[name]
    raise AttributeError(name)

__all__ = [
    "AuthenticatedPrincipal",
    "AutomationApiAuth",
    "AutomationApiServer",
    "AutomationApiSettings",
    "AutomationApiSettingsError",
]
