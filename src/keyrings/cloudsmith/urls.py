"""Cloudsmith service URL classification."""

from __future__ import annotations

from enum import Enum, auto
from urllib.parse import urlsplit

OFFICIAL_PYTHON_HOSTS = frozenset({"dl.cloudsmith.io", "python.cloudsmith.io"})
_CLOUDSMITH_SUFFIXES = (".cloudsmith.io", ".cloudsmith.com")


class HostKind(Enum):
    """How a keyring service relates to Cloudsmith Python registries."""

    OFFICIAL = auto()
    CUSTOM_CANDIDATE = auto()
    UNSUPPORTED = auto()


def classify_service(service: str) -> tuple[HostKind, str | None]:
    """Classify a URL or host while rejecting non-Python Cloudsmith services."""
    hostname = _extract_hostname(service)
    if hostname is None:
        return HostKind.UNSUPPORTED, None
    if hostname in OFFICIAL_PYTHON_HOSTS:
        return HostKind.OFFICIAL, hostname
    if hostname in {"cloudsmith.io", "cloudsmith.com"} or hostname.endswith(
        _CLOUDSMITH_SUFFIXES
    ):
        return HostKind.UNSUPPORTED, hostname
    return HostKind.CUSTOM_CANDIDATE, hostname


def _extract_hostname(service: str) -> str | None:
    value = service.strip()
    if not value:
        return None
    try:
        parsed = urlsplit(value if "://" in value else f"//{value}")
        hostname = parsed.hostname
    except ValueError:
        return None
    return hostname.casefold() if hostname else None
