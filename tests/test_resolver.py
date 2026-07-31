from types import SimpleNamespace

import pytest

from keyrings.cloudsmith import resolver


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    for name in tuple(resolver.os.environ):
        if name.startswith("CLOUDSMITH_"):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_resolves_environment_credential_with_cli_context(monkeypatch):
    captured = {}
    session = object()
    result = SimpleNamespace(api_key="resolved-token", auth_type="bearer")

    class FakeChain:
        def resolve(self, context):
            captured["context"] = context
            return result

    def fake_session(**kwargs):
        captured["session_options"] = kwargs
        return session

    monkeypatch.setenv("CLOUDSMITH_API_KEY", " env-token ")
    monkeypatch.setenv("CLOUDSMITH_API_HOST", "http://localhost:8080/")
    monkeypatch.setenv("CLOUDSMITH_API_PROXY", "http://proxy.example")
    monkeypatch.setenv("CLOUDSMITH_API_HEADERS", "X-Test=value")
    monkeypatch.setenv("CLOUDSMITH_WITHOUT_API_SSL_VERIFY", "true")
    monkeypatch.setenv("CLOUDSMITH_ORG", " acme ")
    monkeypatch.setenv("CLOUDSMITH_SERVICE_SLUG", "ci")
    monkeypatch.setenv("CLOUDSMITH_OIDC_AUDIENCE", "audience")
    monkeypatch.setenv("CLOUDSMITH_OIDC_DISCOVERY_DISABLED", "yes")
    monkeypatch.setenv("CLOUDSMITH_OIDC_DETECTOR_ORDER", "generic")
    monkeypatch.setenv("CLOUDSMITH_OIDC_AWS_DISABLED", "true")
    monkeypatch.setattr(resolver, "CredentialProviderChain", FakeChain)
    monkeypatch.setattr(resolver, "create_requests_session", fake_session)

    credential = resolver.resolve_credential()

    assert credential == resolver.ResolvedCredential(
        password="resolved-token",
        auth_type="bearer",
        api_host="http://localhost:8080",
        org="acme",
    )
    context = captured["context"]
    assert context.session is session
    assert context.api_key_from_env == "env-token"
    assert context.api_host == "http://localhost:8080"
    assert context.oidc_org == "acme"
    assert context.oidc_service_slug == "ci"
    assert context.oidc_audience == "audience"
    assert context.oidc_discovery_disabled is True
    assert context.oidc_detector_order == "generic"
    assert context.oidc_disabled_detectors == frozenset({"aws"})
    assert captured["session_options"]["proxy"] == "http://proxy.example"
    assert captured["session_options"]["ssl_verify"] is False
    assert captured["session_options"]["headers"] == {"X-Test": "value"}


def test_loads_profile_from_explicit_config_files(monkeypatch, tmp_path):
    config_path = tmp_path / "config.ini"
    credentials_path = tmp_path / "credentials.ini"
    config_path.write_text(
        "[default]\noidc_org=default\n"
        "[profile:prod]\noidc_org=production\noidc_service_slug=builder\n"
    )
    credentials_path.write_text(
        "[default]\napi_key=default-key\n[profile:prod]\napi_key=profile-key\n"
    )
    monkeypatch.setenv("CLOUDSMITH_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("CLOUDSMITH_CREDENTIALS_FILE", str(credentials_path))
    monkeypatch.setenv("CLOUDSMITH_PROFILE", "prod")

    options, profile, loaded_credentials = resolver._load_options()

    assert profile == "prod"
    assert loaded_credentials == str(credentials_path)
    assert options.api_key == "profile-key"
    assert options.oidc_org == "production"
    assert options.oidc_service_slug == "builder"


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
    options, _, _ = resolver._load_options()

    with pytest.raises(ValueError, match="untrusted Cloudsmith API host"):
        resolver._api_host(options)


def test_accepts_cloudsmith_api_host_from_working_directory(tmp_path):
    (tmp_path / "config.ini").write_text(
        "[default]\napi_host=https://api.cloudsmith.io/\n"
    )
    options, _, _ = resolver._load_options()

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


def test_returns_none_when_chain_has_no_credentials(monkeypatch):
    class EmptyChain:
        def resolve(self, context):
            return None

    monkeypatch.setattr(resolver, "CredentialProviderChain", EmptyChain)

    assert resolver.resolve_credential() is None


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


def test_merges_disabled_detector_names():
    assert resolver._disabled_detectors(" AWS, generic, ,GITHUB ") == frozenset(
        {"aws", "generic", "github"}
    )
