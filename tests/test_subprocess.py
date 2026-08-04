# ruff: noqa: D100,D103,I001

import subprocess
import sys


PATCH_BACKEND = """
import keyring.backend
from keyrings.cloudsmith.backend import CloudsmithKeyring
from keyrings.cloudsmith.resolver import ResolvedCredential

for backend in keyring.backend.get_all_keyring():
    if isinstance(backend, CloudsmithKeyring):
        backend._resolver = lambda: ResolvedCredential(
            password="subprocess-saml-token",
            api_host="https://api.cloudsmith.io",
        )
        backend._authenticator = lambda owner: None

from keyring.cli import main
main()
"""


def run_keyring(*arguments):
    return subprocess.run(
        [sys.executable, "-c", PATCH_BACKEND, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_keyring_password_mode_used_by_uv_with_username():
    result = run_keyring(
        "get",
        "https://dl.cloudsmith.io/basic/expensify/dev/python/simple/",
        "token",
    )

    assert result.returncode == 0
    assert result.stdout == "subprocess-saml-token\n"


def test_keyring_credential_mode_used_by_uv_without_username():
    result = run_keyring(
        "get",
        "https://dl.cloudsmith.io/basic/expensify/dev/python/simple/",
        "--mode",
        "creds",
    )

    assert result.returncode == 0
    assert result.stdout == "token\nsubprocess-saml-token\n"


def test_keyring_refuses_non_cloudsmith_service():
    result = run_keyring("get", "https://pypi.org/simple", "token")

    assert result.returncode == 1
    assert result.stdout == ""
