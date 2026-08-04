# ruff: noqa: ARG001,ARG005,D100,D103

import logging

import pytest

from keyrings.cloudsmith.backend import CloudsmithKeyring
from keyrings.cloudsmith.resolver import ResolvedCredential


@pytest.fixture
def credential():
    return ResolvedCredential(
        password="saml-access-token",
        api_host="https://api.cloudsmith.io",
    )


def test_reuses_existing_saml_credential_without_authenticating(credential):
    authenticated = False

    def authenticate(owner):
        nonlocal authenticated
        authenticated = True

    backend = CloudsmithKeyring(lambda: credential, authenticate)

    assert (
        backend.get_password(
            "https://dl.cloudsmith.io/basic/expensify/dev/python/simple/", "token"
        )
        == "saml-access-token"
    )
    assert authenticated is False


def test_runs_cli_auth_and_retries_for_download_url(credential):
    credentials = iter((None, credential))
    owners = []
    backend = CloudsmithKeyring(lambda: next(credentials), owners.append)

    assert (
        backend.get_password(
            "https://dl.cloudsmith.io/basic/expensify/dev/python/simple/", "token"
        )
        == "saml-access-token"
    )
    assert owners == ["expensify"]


def test_runs_cli_auth_for_publish_url(credential):
    credentials = iter((None, credential))
    owners = []
    backend = CloudsmithKeyring(lambda: next(credentials), owners.append)

    result = backend.get_credential("https://python.cloudsmith.io/expensify/dev/", None)

    assert result is not None
    assert result.username == "token"
    assert result.password == "saml-access-token"
    assert owners == ["expensify"]


def test_does_not_authenticate_when_owner_cannot_be_inferred():
    authenticated = False

    def authenticate(owner):
        nonlocal authenticated
        authenticated = True

    backend = CloudsmithKeyring(lambda: None, authenticate)

    assert backend.get_password("dl.cloudsmith.io", "token") is None
    assert backend.get_credential("dl.cloudsmith.io", None) is None
    assert authenticated is False


def test_rejects_other_username_without_resolving():
    resolved = False

    def resolver():
        nonlocal resolved
        resolved = True

    backend = CloudsmithKeyring(resolver)

    assert backend.get_password("dl.cloudsmith.io", "alice") is None
    assert backend.get_credential("dl.cloudsmith.io", "alice") is None
    assert resolved is False


def test_rejects_unsupported_service_without_resolving():
    resolved = False

    def resolver():
        nonlocal resolved
        resolved = True

    backend = CloudsmithKeyring(resolver)

    assert backend.get_password("api.cloudsmith.io", "token") is None
    assert resolved is False


def test_custom_domain_uses_org_for_auth_and_validation(monkeypatch, credential):
    credentials = iter((None, credential))
    owners = []

    def fake_domains(org, backend_kind, **kwargs):
        assert org == "expensify"
        assert int(backend_kind) == 3
        assert kwargs == {
            "api_key": "saml-access-token",
            "auth_type": "bearer",
            "api_host": "https://api.cloudsmith.io",
        }
        return ["Packages.Example.com"]

    monkeypatch.setenv("CLOUDSMITH_ORG", " expensify ")
    monkeypatch.setattr(
        "cloudsmith_cli.credential_helpers.custom_domains.get_format_domains",
        fake_domains,
    )
    backend = CloudsmithKeyring(lambda: next(credentials), owners.append)

    assert (
        backend.get_password("https://packages.example.com/simple", "token")
        == "saml-access-token"
    )
    assert owners == ["expensify"]


def test_custom_domain_requires_valid_org(monkeypatch, credential):
    monkeypatch.setenv("CLOUDSMITH_ORG", "invalid owner!")
    backend = CloudsmithKeyring(lambda: credential)

    assert backend.get_password("packages.example.com", "token") is None


def test_custom_domain_must_be_registered(monkeypatch, credential):
    monkeypatch.setenv("CLOUDSMITH_ORG", "expensify")
    monkeypatch.setattr(
        "cloudsmith_cli.credential_helpers.custom_domains.get_format_domains",
        lambda *args, **kwargs: ["other.example.com"],
    )

    assert (
        CloudsmithKeyring(lambda: credential).get_password(
            "packages.example.com", "token"
        )
        is None
    )


def test_resolution_or_auth_errors_degrade_to_not_found(caplog):
    def fail():
        raise RuntimeError("secret must not be logged")

    with caplog.at_level(logging.WARNING):
        result = CloudsmithKeyring(fail).get_password(
            "https://dl.cloudsmith.io/basic/expensify/dev", "token"
        )

    assert result is None
    assert caplog.messages == ["Unable to retrieve Cloudsmith keyring credentials"]
    assert "secret must not be logged" not in caplog.text


def test_warns_when_authentication_does_not_produce_token(caplog):
    with caplog.at_level(logging.WARNING):
        result = CloudsmithKeyring(lambda: None, lambda owner: None).get_password(
            "https://dl.cloudsmith.io/basic/expensify/dev", "token"
        )

    assert result is None
    assert caplog.messages == [
        "Cloudsmith authentication completed without a usable token"
    ]


def test_backend_is_read_only():
    backend = CloudsmithKeyring()

    with pytest.raises(NotImplementedError):
        backend.set_password("service", "user", "password")
    with pytest.raises(NotImplementedError):
        backend.delete_password("service", "user")
