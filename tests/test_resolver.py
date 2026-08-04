# ruff: noqa: ARG002,D100,D103,SLF001

from types import SimpleNamespace

import pytest

from keyrings.cloudsmith import resolver


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    for name in tuple(resolver.os.environ):
        if name.startswith("CLOUDSMITH_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_resolves_only_saml_keyring_credential(monkeypatch):
    captured = {}
    session = object()
    result = SimpleNamespace(api_key="saml-token", auth_type="bearer")

    class FakeProvider:
        def resolve(self, context):
            captured["context"] = context
            return result

    def fake_session(**kwargs):
        captured["session_options"] = kwargs
        return session

    monkeypatch.setenv("CLOUDSMITH_API_KEY", "ignored-api-key")
    monkeypatch.setenv("CLOUDSMITH_API_HOST", "http://localhost:8080/")
    monkeypatch.setenv("CLOUDSMITH_API_PROXY", "http://proxy.example")
    monkeypatch.setenv("CLOUDSMITH_API_HEADERS", "X-Test=value")
    monkeypatch.setenv("CLOUDSMITH_WITHOUT_API_SSL_VERIFY", "true")
    monkeypatch.setenv("CLOUDSMITH_OIDC_TOKEN", "ignored-oidc-token")
    monkeypatch.setattr(resolver, "SAMLKeyringProvider", FakeProvider)
    monkeypatch.setattr(resolver, "create_requests_session", fake_session)

    credential = resolver.resolve_credential()

    assert credential == resolver.ResolvedCredential(
        password="saml-token", api_host="http://localhost:8080"
    )
    context = captured["context"]
    assert context.session is session
    assert context.api_host == "http://localhost:8080"
    assert context.api_key_from_env is None
    assert context.api_key_from_file is None
    assert context.oidc_org is None
    assert context.oidc_service_slug is None
    assert captured["session_options"]["proxy"] == "http://proxy.example"
    assert captured["session_options"]["ssl_verify"] is False
    assert captured["session_options"]["headers"] == {"X-Test": "value"}


@pytest.mark.parametrize(
    "result",
    [None, SimpleNamespace(api_key="api-key", auth_type="api_key")],
)
def test_rejects_missing_or_non_saml_credentials(monkeypatch, result):
    class FakeProvider:
        def resolve(self, context):
            return result

    monkeypatch.setattr(resolver, "SAMLKeyringProvider", FakeProvider)

    assert resolver.resolve_credential() is None


def test_loads_profile_from_explicit_noncredential_config(monkeypatch, tmp_path):
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        "[default]\napi_host=https://api.cloudsmith.io\n"
        "[profile:prod]\napi_host=https://api.cloudsmith.com\n"
    )
    monkeypatch.setenv("CLOUDSMITH_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("CLOUDSMITH_PROFILE", "prod")

    options = resolver._load_options()

    assert options.api_host == "https://api.cloudsmith.com"


def test_ignores_credentials_file_configuration(monkeypatch, tmp_path):
    missing = tmp_path / "missing-credentials.ini"
    monkeypatch.setenv("CLOUDSMITH_CREDENTIALS_FILE", str(missing))

    resolver._load_options()


def test_rejects_missing_explicit_config(monkeypatch, tmp_path):
    missing = tmp_path / "missing.ini"
    monkeypatch.setenv("CLOUDSMITH_CONFIG_FILE", str(missing))

    with pytest.raises(FileNotFoundError, match="CLOUDSMITH_CONFIG_FILE"):
        resolver.resolve_credential()

    assert resolver._RESOLVING.get() is False


def test_rejects_untrusted_api_host_from_working_directory(tmp_path):
    (tmp_path / "config.ini").write_text(
        "[default]\napi_host=https://attacker.example\n"
    )
    options = resolver._load_options()

    with pytest.raises(ValueError, match="untrusted Cloudsmith API host"):
        resolver._api_host(options)


def test_accepts_cloudsmith_api_host_from_working_directory(tmp_path):
    (tmp_path / "config.ini").write_text(
        "[default]\napi_host=https://api.cloudsmith.io/\n"
    )
    options = resolver._load_options()

    assert resolver._api_host(options) == "https://api.cloudsmith.io"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("https://api.cloudsmith.com", True),
        ("https://cloudsmith.io", True),
        ("http://api.cloudsmith.io", False),
        ("not a URL", False),
        ("https://[invalid", False),
    ],
)
def test_relative_api_host_safety(value, expected):
    assert resolver._safe_relative_api_host(value) is expected


def test_prevents_reentrant_resolution():
    token = resolver._RESOLVING.set(True)
    try:
        assert resolver.resolve_credential() is None
    finally:
        resolver._RESOLVING.reset(token)


@pytest.mark.parametrize(
    "value, default, expected",
    [(None, True, True), ("ON", False, True), ("0", True, False)],
)
def test_environment_boolean(monkeypatch, value, default, expected):
    if value is not None:
        monkeypatch.setenv("CLOUDSMITH_TEST_BOOL", value)

    assert resolver._env_bool("CLOUDSMITH_TEST_BOOL", default) is expected
