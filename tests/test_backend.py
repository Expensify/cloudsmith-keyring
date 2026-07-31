import logging

import pytest

from keyrings.cloudsmith.backend import CloudsmithKeyring
from keyrings.cloudsmith.resolver import ResolvedCredential


@pytest.fixture
def credential():
    return ResolvedCredential(
        password="secret-token",
        auth_type="api_key",
        api_host="https://api.cloudsmith.io",
        org="acme",
    )


def test_returns_password_for_official_service_and_token_username(credential):
    backend = CloudsmithKeyring(lambda: credential)

    assert (
        backend.get_password("https://dl.cloudsmith.io/basic/acme/repo", "token")
        == "secret-token"
    )


def test_rejects_other_username_without_resolving():
    called = False

    def resolver():
        nonlocal called
        called = True

    backend = CloudsmithKeyring(resolver)

    assert backend.get_password("dl.cloudsmith.io", "alice") is None
    assert backend.get_credential("dl.cloudsmith.io", "alice") is None
    assert called is False


@pytest.mark.parametrize("username", [None, "token"])
def test_returns_complete_credential(username, credential):
    result = CloudsmithKeyring(lambda: credential).get_credential(
        "python.cloudsmith.io", username
    )

    assert result is not None
    assert result.username == "token"
    assert result.password == "secret-token"


def test_rejects_unsupported_service_without_resolving():
    called = False

    def resolver():
        nonlocal called
        called = True

    backend = CloudsmithKeyring(resolver)

    assert backend.get_password("api.cloudsmith.io", "token") is None
    assert called is False


def test_returns_none_when_no_cloudsmith_credential_exists():
    backend = CloudsmithKeyring(lambda: None)

    assert backend.get_password("dl.cloudsmith.io", "token") is None
    assert backend.get_credential("dl.cloudsmith.io", None) is None


def test_validates_custom_python_domain(monkeypatch, credential):
    def fake_domains(org, backend_kind, **kwargs):
        assert org == "acme"
        assert int(backend_kind) == 3
        assert kwargs == {
            "api_key": "secret-token",
            "auth_type": "api_key",
            "api_host": "https://api.cloudsmith.io",
        }
        return ["Packages.Example.com"]

    monkeypatch.setattr(
        "cloudsmith_cli.credential_helpers.custom_domains.get_format_domains",
        fake_domains,
    )
    backend = CloudsmithKeyring(lambda: credential)

    assert (
        backend.get_password("https://packages.example.com/simple", "token")
        == "secret-token"
    )
    assert backend.get_password("https://other.example.com/simple", "token") is None


def test_custom_domain_requires_org(credential):
    credential = ResolvedCredential(
        password=credential.password,
        auth_type=credential.auth_type,
        api_host=credential.api_host,
        org=None,
    )

    assert (
        CloudsmithKeyring(lambda: credential).get_password(
            "packages.example.com", "token"
        )
        is None
    )


def test_resolution_errors_degrade_to_not_found(caplog):
    def fail():
        raise RuntimeError("secret must not be logged")

    with caplog.at_level(logging.WARNING):
        result = CloudsmithKeyring(fail).get_password("dl.cloudsmith.io", "token")

    assert result is None
    assert caplog.messages == ["Unable to retrieve Cloudsmith keyring credentials"]
    assert "secret must not be logged" not in caplog.text


def test_custom_domain_errors_degrade_to_not_found(monkeypatch, credential, caplog):
    def fail(*args, **kwargs):
        raise OSError("network detail")

    monkeypatch.setattr(
        "cloudsmith_cli.credential_helpers.custom_domains.get_format_domains", fail
    )

    with caplog.at_level(logging.WARNING):
        result = CloudsmithKeyring(lambda: credential).get_password(
            "packages.example.com", "token"
        )

    assert result is None
    assert caplog.messages == ["Unable to retrieve Cloudsmith keyring credentials"]
    assert "network detail" not in caplog.text


def test_backend_is_read_only():
    backend = CloudsmithKeyring()

    with pytest.raises(NotImplementedError):
        backend.set_password("service", "user", "password")
    with pytest.raises(NotImplementedError):
        backend.delete_password("service", "user")
