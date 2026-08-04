"""Cloudsmith service URL classification."""

from __future__ import annotations

import re
from enum import Enum, auto
from urllib.parse import unquote, urlsplit

OFFICIAL_PYTHON_HOSTS = frozenset({"dl.cloudsmith.io", "python.cloudsmith.io"})
_CLOUDSMITH_SUFFIXES = (".cloudsmith.io", ".cloudsmith.com")
_OWNER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


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


def repository_owner(service: str) -> str | None:
    """Infer the Cloudsmith workspace from an official Python repository URL."""
    parsed = _parse_service(service)
    if parsed is None or parsed.hostname is None:
        return None

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    hostname = parsed.hostname.casefold()
    if hostname == "dl.cloudsmith.io":
        if len(parts) < 2 or parts[0] != "basic":
            return None
        return normalize_owner(parts[1])
    if hostname == "python.cloudsmith.io" and parts:
        return normalize_owner(parts[0])
    return None


def normalize_owner(value: str) -> str | None:
    """Strip and validate a Cloudsmith workspace slug."""
    owner = value.strip()
    return owner if _OWNER_PATTERN.fullmatch(owner) else None


def _extract_hostname(service: str) -> str | None:
    parsed = _parse_service(service)
    return parsed.hostname.casefold() if parsed and parsed.hostname else None


def _parse_service(service: str):
    """Parse a keyring service supplied as either a URL or a host."""
    value = service.strip()
    if not value:
        return None
    try:
        return urlsplit(value if "://" in value else f"//{value}")
    except ValueError:
        return None
