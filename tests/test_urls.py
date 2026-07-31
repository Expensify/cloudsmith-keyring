import pytest

from keyrings.cloudsmith.urls import HostKind, classify_service


@pytest.mark.parametrize(
    "service, expected_host",
    [
        ("dl.cloudsmith.io", "dl.cloudsmith.io"),
        ("DL.CLOUDSMITH.IO:443", "dl.cloudsmith.io"),
        (
            "https://token@dl.cloudsmith.io/basic/acme/repo/python/simple/",
            "dl.cloudsmith.io",
        ),
        ("https://python.cloudsmith.io/acme/repo/", "python.cloudsmith.io"),
    ],
)
def test_classifies_official_python_services(service, expected_host):
    assert classify_service(service) == (HostKind.OFFICIAL, expected_host)


@pytest.mark.parametrize(
    "service",
    [
        "",
        "://",
        "https://[invalid",
        "api.cloudsmith.io",
        "docker.cloudsmith.io",
        "cloudsmith.io",
        "packages.cloudsmith.com",
    ],
)
def test_rejects_invalid_and_non_python_cloudsmith_services(service):
    assert classify_service(service)[0] is HostKind.UNSUPPORTED


@pytest.mark.parametrize(
    "service, expected_host",
    [
        ("packages.example.com", "packages.example.com"),
        ("https://packages.example.com/simple/", "packages.example.com"),
        ("evilcloudsmith.io", "evilcloudsmith.io"),
    ],
)
def test_classifies_external_hosts_as_custom_candidates(service, expected_host):
    assert classify_service(service) == (HostKind.CUSTOM_CANDIDATE, expected_host)
