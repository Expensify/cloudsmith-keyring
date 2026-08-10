# ruff: noqa: ARG001,ARG005,D100,D103,SLF001

import io
import subprocess
from contextlib import contextmanager

import pytest

from keyrings.cloudsmith import auth


def test_authenticate_runs_cloudsmith_cli_with_protocol_safe_output(monkeypatch):
    captured = {}
    terminal = io.StringIO()

    @contextmanager
    def fake_stdin():
        yield terminal

    def fake_runner(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(auth, "_authentication_stdin", fake_stdin)

    auth.authenticate("expensify", runner=fake_runner)

    assert captured["command"] == [
        auth.sys.executable,
        "-m",
        "cloudsmith_cli",
        "auth",
        "--owner",
        "expensify",
    ]
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"]["stdin"] is terminal
    assert captured["kwargs"]["stdout"] is auth.sys.stderr
    assert captured["kwargs"]["stderr"] is auth.sys.stderr
    assert captured["kwargs"]["env"]["PYTHONUNBUFFERED"] == "1"


def test_authenticate_raises_when_cli_fails(monkeypatch):
    @contextmanager
    def fake_stdin():
        yield None

    monkeypatch.setattr(auth, "_authentication_stdin", fake_stdin)

    with pytest.raises(auth.AuthenticationError, match="status 7"):
        auth.authenticate(
            "expensify",
            runner=lambda *args, **kwargs: subprocess.CompletedProcess(
                [], returncode=7
            ),
        )


@pytest.mark.parametrize(
    "os_name, expected", [("nt", ("CONIN$",)), ("posix", ("/dev/tty",))]
)
def test_tty_devices(os_name, expected):
    assert auth._tty_devices(os_name) == expected


def test_authentication_stdin_uses_controlling_terminal(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(auth.Path, "open", lambda *args, **kwargs: stream)

    with auth._authentication_stdin() as result:
        assert result is stream

    assert stream.closed is True


def test_authentication_stdin_falls_back_to_inherited_stdin(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError

    monkeypatch.setattr(auth.Path, "open", fail)

    with auth._authentication_stdin() as result:
        assert result is None
