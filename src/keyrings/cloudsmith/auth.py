"""Launch the Cloudsmith CLI SAML authentication flow."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any


class AuthenticationError(RuntimeError):
    """Raised when the Cloudsmith CLI authentication flow fails."""


def authenticate(
    owner: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> None:
    """Authenticate an owner through the installed Cloudsmith CLI."""
    command = [
        sys.executable,
        "-m",
        "cloudsmith_cli",
        "auth",
        "--owner",
        owner,
    ]
    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"

    with _authentication_stdin() as auth_stdin:
        result = runner(
            command,
            check=False,
            env=environment,
            stdin=auth_stdin,
            stdout=sys.stderr,
            stderr=sys.stderr,
        )

    if result.returncode != 0:
        raise AuthenticationError(
            f"Cloudsmith CLI authentication exited with status {result.returncode}"
        )


@contextmanager
def _authentication_stdin() -> Iterator[IO[str] | None]:
    """Use the controlling terminal even when uv gives keyring no stdin."""
    for device in _tty_devices(os.name):
        try:
            with Path(device).open(encoding="utf-8") as stream:
                yield stream
                return
        except OSError:
            continue
    yield None


def _tty_devices(os_name: str) -> tuple[str, ...]:
    """Return controlling-terminal device names for an operating system."""
    return ("CONIN$",) if os_name == "nt" else ("/dev/tty",)
