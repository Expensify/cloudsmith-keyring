import os
import subprocess
import sys


def run_keyring(*arguments):
    env = os.environ.copy()
    env["CLOUDSMITH_API_KEY"] = "subprocess-secret"
    return subprocess.run(
        [sys.executable, "-m", "keyring", *arguments],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )


def test_keyring_password_mode_used_by_uv_with_username():
    result = run_keyring("get", "https://dl.cloudsmith.io/basic/acme/repo", "token")

    assert result.returncode == 0
    assert result.stdout == "subprocess-secret\n"


def test_keyring_credential_mode_used_by_uv_without_username():
    result = run_keyring(
        "get", "https://dl.cloudsmith.io/basic/acme/repo", "--mode", "creds"
    )

    assert result.returncode == 0
    assert result.stdout == "token\nsubprocess-secret\n"


def test_keyring_refuses_non_cloudsmith_service():
    result = run_keyring("get", "https://pypi.org/simple", "token")

    assert result.returncode == 1
    assert result.stdout == ""
