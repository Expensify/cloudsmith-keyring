"""Resolve only SAML credentials stored by the Cloudsmith CLI auth flow."""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from cloudsmith_cli.cli.config import ConfigReader, Options
from cloudsmith_cli.core.credentials.models import CredentialContext
from cloudsmith_cli.core.credentials.providers.keyring_provider import (
    KeyringProvider as SAMLKeyringProvider,
)
from cloudsmith_cli.core.rest import create_requests_session

DEFAULT_API_HOST = "https://api.cloudsmith.io"
_RESOLVING: ContextVar[bool] = ContextVar("cloudsmith_keyring_resolving", default=False)


@dataclass(frozen=True)
class ResolvedCredential:
    """A Cloudsmith SAML token and its API endpoint."""

    password: str
    api_host: str

    def is_custom_python_domain(self, hostname: str, owner: str) -> bool:
        """Validate a hostname against an owner's Python custom domains."""
        from cloudsmith_cli.credential_helpers.backends import BackendKind
        from cloudsmith_cli.credential_helpers.custom_domains import get_format_domains

        domains = get_format_domains(
            owner,
            BackendKind.PYTHON,
            api_key=self.password,
            auth_type="bearer",
            api_host=self.api_host,
        )
        return hostname.casefold() in {domain.casefold() for domain in domains}


def resolve_credential() -> ResolvedCredential | None:
    """Return a valid SAML token from Cloudsmith's system-keyring provider."""
    if _RESOLVING.get():
        return None

    reset_token = _RESOLVING.set(True)
    try:
        options = _load_options()
        api_host = _api_host(options)
        session = create_requests_session(
            proxy=_environment_or_option("CLOUDSMITH_API_PROXY", options.api_proxy),
            ssl_verify=_ssl_verify(options),
            user_agent=options.api_user_agent,
            headers=_api_headers(options),
        )
        context = CredentialContext(session=session, api_host=api_host)
        result = SAMLKeyringProvider().resolve(context)
        if result is None or result.auth_type != "bearer":
            return None
        return ResolvedCredential(password=result.api_key, api_host=api_host)
    finally:
        _RESOLVING.reset(reset_token)


def _load_options() -> Options:
    """Load only non-credential CLI configuration in isolated readers."""

    class IsolatedConfigReader(ConfigReader):
        config_files = list(ConfigReader.config_files)
        config_searchpath = list(ConfigReader.config_searchpath)

    class IsolatedOptions(Options):
        @staticmethod
        def get_config_reader():
            return IsolatedConfigReader

    profile = _nonempty_env("CLOUDSMITH_PROFILE")
    config_file = _configured_path("CLOUDSMITH_CONFIG_FILE")
    options = IsolatedOptions()
    options.load_config_file(config_file, profile=profile)
    return options


def _configured_path(name: str) -> str | None:
    """Return an explicitly configured path after checking it exists."""
    value = _nonempty_env(name)
    if value and not Path(value).exists():
        raise FileNotFoundError(f"{name} does not exist")
    return value


def _api_host(options: Options) -> str:
    """Resolve the API host while rejecting untrusted working-directory config."""
    explicit_host = _nonempty_env("CLOUDSMITH_API_HOST")
    host = explicit_host or options.api_host or DEFAULT_API_HOST
    if explicit_host is None:
        relative_host = ConfigReader.read_relative_config_value(
            "api_host", profile=_nonempty_env("CLOUDSMITH_PROFILE")
        )
        untrusted_host = relative_host and not _safe_relative_api_host(host)
        if host == relative_host and untrusted_host:
            raise ValueError("Refusing an untrusted Cloudsmith API host")
    return host.rstrip("/")


def _safe_relative_api_host(value: str) -> bool:
    """Check whether a relative config points to a Cloudsmith HTTPS host."""
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
    except ValueError:
        return False
    return parsed.scheme == "https" and (
        hostname in {"cloudsmith.io", "cloudsmith.com"}
        or hostname.endswith(".cloudsmith.io")
        or hostname.endswith(".cloudsmith.com")
    )


def _api_headers(options: Options) -> dict[str, str] | None:
    """Apply API headers explicitly provided through the environment."""
    value = _nonempty_env("CLOUDSMITH_API_HEADERS")
    if value:
        options.api_headers = value
    return options.api_headers


def _ssl_verify(options: Options) -> bool:
    """Resolve the CLI's inverse SSL verification setting."""
    return not _env_bool(
        "CLOUDSMITH_WITHOUT_API_SSL_VERIFY", not options.api_ssl_verify
    )


def _environment_or_option(name: str, option: str | None) -> str | None:
    """Prefer a non-empty environment value to CLI configuration."""
    return _nonempty_env(name) or option


def _nonempty_env(name: str) -> str | None:
    """Read and strip a non-empty environment variable."""
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _env_bool(name: str, default: bool) -> bool:
    """Parse the boolean environment forms accepted by the CLI."""
    value = _nonempty_env(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on"}
