"""Read-only keyring backend for Cloudsmith Python repositories."""

from __future__ import annotations

import logging
from collections.abc import Callable

from keyring.backend import KeyringBackend
from keyring.credentials import SimpleCredential

from .resolver import ResolvedCredential, resolve_credential
from .urls import HostKind, classify_service

logger = logging.getLogger(__name__)

TOKEN_USERNAME = "token"


class CloudsmithKeyring(KeyringBackend):
    """Supply Cloudsmith CLI credentials to Python package clients."""

    priority = 9

    def __init__(
        self,
        resolver: Callable[[], ResolvedCredential | None] = resolve_credential,
    ) -> None:
        super().__init__()
        self._resolver = resolver

    def get_password(self, service: str, username: str) -> str | None:
        """Return a Cloudsmith token for the supported Basic Auth username."""
        if username != TOKEN_USERNAME:
            return None

        credential = self._credential_for(service)
        return credential.password if credential else None

    def get_credential(
        self, service: str, username: str | None
    ) -> SimpleCredential | None:
        """Return both Basic Auth fields when a client omits the username."""
        if username not in (None, TOKEN_USERNAME):
            return None

        credential = self._credential_for(service)
        if credential is None:
            return None
        return SimpleCredential(TOKEN_USERNAME, credential.password)

    def set_password(self, service: str, username: str, password: str) -> None:
        """Reject writes so the chainer can delegate to a storage backend."""
        raise NotImplementedError

    def delete_password(self, service: str, username: str) -> None:
        """Reject deletes so the chainer can delegate to a storage backend."""
        raise NotImplementedError

    def _credential_for(self, service: str) -> ResolvedCredential | None:
        kind, hostname = classify_service(service)
        if kind is HostKind.UNSUPPORTED:
            return None

        try:
            credential = self._resolver()
            if credential is None:
                return None
            if kind is HostKind.OFFICIAL:
                return credential
            if hostname and credential.is_custom_python_domain(hostname):
                return credential
        except Exception:  # Keyring lookups must degrade to "not found".
            logger.warning("Unable to retrieve Cloudsmith keyring credentials")
            return None
        return None
