"""Adapter around the Cloudsmith CLI credential provider chain."""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from cloudsmith_cli.cli.config import (
    ConfigReader,
    CredentialsReader,
    Options,
)
from cloudsmith_cli.core.credentials.chain import CredentialProviderChain
from cloudsmith_cli.core.credentials.models import CredentialContext
from cloudsmith_cli.core.credentials.oidc.detectors import disabled_detectors_from_env
from cloudsmith_cli.core.rest import create_requests_session

logger = logging.getLogger(__name__)

DEFAULT_API_HOST = "https://api.cloudsmith.io"
_RESOLVING: ContextVar[bool] = ContextVar("cloudsmith_keyring_resolving", default=False)


@dataclass(frozen=True)
class ResolvedCredential:
    """A Cloudsmith credential and the context needed for domain validation."""

    password: str
    auth_type: str
    api_host: str
    org: str | None

    def is_custom_python_domain(self, hostname: str) -> bool:
        """Validate a hostname against the account's Python custom domains."""
        if not self.org:
            return False

        from cloudsmith_cli.credential_helpers.backends import BackendKind
        from cloudsmith_cli.credential_helpers.custom_domains import get_format_domains

        domains = get_format_domains(
            self.org,
            BackendKind.PYTHON,
            api_key=self.password,
            auth_type=self.auth_type,
            api_host=self.api_host,
        )
        return hostname.casefold() in {domain.casefold() for domain in domains}


def resolve_credential() -> ResolvedCredential | None:
    """Resolve credentials using the same source order as the Cloudsmith CLI."""
    if _RESOLVING.get():
        return None

    reset_token = _RESOLVING.set(True)
    try:
        options, profile, credentials_file = _load_options()
        api_host = _api_host(options)
        session = create_requests_session(
            proxy=_environment_or_option("CLOUDSMITH_API_PROXY", options.api_proxy),
            ssl_verify=_ssl_verify(options),
            user_agent=options.api_user_agent,
            headers=_api_headers(options),
        )
        disabled = disabled_detectors_from_env(os.environ) | _disabled_detectors(
            options.oidc_disabled_detectors
        )
        context = CredentialContext(
            session=session,
            api_key_from_env=_nonempty_env("CLOUDSMITH_API_KEY"),
            api_key_from_file=options.api_key,
            api_host=api_host,
            creds_file_path=credentials_file,
            profile=profile,
            oidc_audience=_environment_or_option(
                "CLOUDSMITH_OIDC_AUDIENCE", options.oidc_audience
            ),
            oidc_org=_environment_or_option("CLOUDSMITH_ORG", options.oidc_org),
            oidc_service_slug=_environment_or_option(
                "CLOUDSMITH_SERVICE_SLUG", options.oidc_service_slug
            ),
            oidc_discovery_disabled=_env_bool(
                "CLOUDSMITH_OIDC_DISCOVERY_DISABLED",
                options.oidc_discovery_disabled,
            ),
            oidc_detector_order=_environment_or_option(
                "CLOUDSMITH_OIDC_DETECTOR_ORDER", options.oidc_detector_order
            ),
            oidc_disabled_detectors=disabled,
        )
        result = CredentialProviderChain().resolve(context)
        if result is None:
            return None
        return ResolvedCredential(
            password=result.api_key,
            auth_type=result.auth_type,
            api_host=api_host,
            org=context.oidc_org or _nonempty_env("CLOUDSMITH_ORG"),
        )
    finally:
        _RESOLVING.reset(reset_token)


def _load_options() -> tuple[Options, str | None, str | None]:
    """Load CLI files without mutating Cloudsmith's global reader classes."""

    class IsolatedConfigReader(ConfigReader):
        config_files = list(ConfigReader.config_files)
        config_searchpath = list(ConfigReader.config_searchpath)

    class IsolatedCredentialsReader(CredentialsReader):
        config_files = list(CredentialsReader.config_files)
        config_searchpath = list(CredentialsReader.config_searchpath)

    class IsolatedOptions(Options):
        @staticmethod
        def get_config_reader():
            return IsolatedConfigReader

        @staticmethod
        def get_creds_reader():
            return IsolatedCredentialsReader

    profile = _nonempty_env("CLOUDSMITH_PROFILE")
    config_file = _configured_path("CLOUDSMITH_CONFIG_FILE")
    credentials_file = _configured_path("CLOUDSMITH_CREDENTIALS_FILE")
    options = IsolatedOptions()
    options.load_config_file(config_file, profile=profile)
    options.load_creds_file(credentials_file, profile=profile)
    return options, profile, credentials_file


def _configured_path(name: str) -> str | None:
    value = _nonempty_env(name)
    if value and not Path(value).exists():
        raise FileNotFoundError(f"{name} does not exist")
    return value


def _api_host(options: Options) -> str:
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
    value = _nonempty_env("CLOUDSMITH_API_HEADERS")
    if value:
        options.api_headers = value
    return options.api_headers


def _ssl_verify(options: Options) -> bool:
    return not _env_bool(
        "CLOUDSMITH_WITHOUT_API_SSL_VERIFY", not options.api_ssl_verify
    )


def _disabled_detectors(value: str | None) -> frozenset[str]:
    return frozenset(
        detector.strip().lower()
        for detector in (value or "").split(",")
        if detector.strip()
    )


def _environment_or_option(name: str, option: str | None) -> str | None:
    return _nonempty_env(name) or option


def _nonempty_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _env_bool(name: str, default: bool) -> bool:
    value = _nonempty_env(name)
    if value is None:
        return default
    return value.casefold() in {"1", "true", "yes", "on"}
