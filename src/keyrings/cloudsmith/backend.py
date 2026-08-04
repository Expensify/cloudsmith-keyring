"""Read-only keyring backend for Cloudsmith Python repositories."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from keyring.backend import KeyringBackend
from keyring.credentials import SimpleCredential

from .auth import authenticate
from .resolver import ResolvedCredential, resolve_credential
from .urls import HostKind, classify_service, normalize_owner, repository_owner

logger = logging.getLogger(__name__)

TOKEN_USERNAME = "token"


class CloudsmithKeyring(KeyringBackend):
    """Supply Cloudsmith CLI credentials to Python package clients."""

    priority = 9

    def __init__(
        self,
        resolver: Callable[[], ResolvedCredential | None] = resolve_credential,
        authenticator: Callable[[str], None] = authenticate,
    ) -> None:
        """Create a backend with injectable auth collaborators for testing."""
        super().__init__()
        self._resolver = resolver
        self._authenticator = authenticator

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

        owner = repository_owner(service)
        if kind is HostKind.CUSTOM_CANDIDATE:
            owner = normalize_owner(os.environ.get("CLOUDSMITH_ORG", ""))
            if owner is None:
                return None

        try:
            credential = self._resolver()
            if credential is None:
                if owner is None:
                    return None
                self._authenticator(owner)
                credential = self._resolver()
                if credential is None:
                    logger.warning(
                        "Cloudsmith authentication completed without a usable token"
                    )
                    return None
            if kind is HostKind.OFFICIAL:
                return credential
            if (
                hostname
                and owner
                and credential.is_custom_python_domain(hostname, owner)
            ):
                return credential
        except Exception:  # noqa: BLE001 - Keyring lookups degrade to "not found".
            logger.warning("Unable to retrieve Cloudsmith keyring credentials")
            return None
        return None
