"""Independent local-session and remote-key authentication."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from typing import FrozenSet


MATHCRAFT_PERMISSION = "recognition.mathcraft"
EXTERNAL_PERMISSION = "recognition.external"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    id: str
    kind: str
    permissions: FrozenSet[str]

    def allows(self, permission: str) -> bool:
        return permission in self.permissions


class AutomationApiAuth:
    def __init__(
        self,
        *,
        local_token: str | None = None,
        remote_key: str | None = None,
        remote_external_enabled: bool = False,
    ) -> None:
        self._local_token = local_token or secrets.token_urlsafe(32)
        self._remote_key = str(remote_key or "").strip()
        self._remote_external_enabled = bool(remote_external_enabled)

    @property
    def local_token(self) -> str:
        return self._local_token

    @property
    def has_remote_key(self) -> bool:
        return bool(self._remote_key)

    @staticmethod
    def generate_remote_key() -> str:
        return secrets.token_urlsafe(32)

    def authenticate(self, header_value: str | None) -> AuthenticatedPrincipal | None:
        prefix = "Bearer "
        if not header_value or not header_value.startswith(prefix):
            return None
        candidate = header_value[len(prefix) :].strip()
        if not candidate:
            return None
        if hmac.compare_digest(candidate, self._local_token):
            return AuthenticatedPrincipal(
                id="local-session",
                kind="local",
                permissions=frozenset((MATHCRAFT_PERMISSION, EXTERNAL_PERMISSION)),
            )
        if self._remote_key and hmac.compare_digest(candidate, self._remote_key):
            permissions = {MATHCRAFT_PERMISSION}
            if self._remote_external_enabled:
                permissions.add(EXTERNAL_PERMISSION)
            return AuthenticatedPrincipal(
                id="remote-key",
                kind="remote",
                permissions=frozenset(permissions),
            )
        return None
