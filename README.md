# cloudsmith-keyring

`cloudsmith-keyring` is a read-only [keyring](https://pypi.org/project/keyring/)
backend that supplies credentials from the
[Cloudsmith CLI](https://github.com/cloudsmith-io/cloudsmith-cli) to Python
package clients. Its primary use case is authenticating
[uv](https://docs.astral.sh/uv/) to private Cloudsmith Python repositories
through uv's subprocess keyring provider.

The backend supports Cloudsmith API keys, profiles, SAML sessions, and OIDC
credential discovery. It returns credentials only for Cloudsmith's official
Python endpoints or API-validated Python custom domains.

## Requirements

- Python 3.10 or later
- uv with subprocess keyring support
- `keyring` 25.4.1 or later
- `cloudsmith-cli` 1.20.1 or later

## Installation

Install the backend alongside the `keyring` executable that uv will find on
`PATH`:

```shell
uv tool install keyring --with cloudsmith-keyring
```

The package depends on `cloudsmith-cli`, so the keyring environment can use the
same credential resolution behavior as the CLI. An existing standalone or
separately installed `cloudsmith` command can still be used to establish the
session.

Confirm that keyring discovered the backend:

```shell
keyring --list-backends
```

The output should include:

```text
keyrings.cloudsmith.backend.CloudsmithKeyring (priority: 9)
```

## Authenticate Cloudsmith

Authenticate using any source supported by the Cloudsmith CLI. The provider
uses the CLI's normal precedence order:

1. `CLOUDSMITH_API_KEY`
2. The selected profile in `credentials.ini`
3. A SAML session stored in the system keyring by `cloudsmith auth`
4. OIDC discovery when `CLOUDSMITH_ORG` and `CLOUDSMITH_SERVICE_SLUG` are set

For example, use an API key:

```shell
export CLOUDSMITH_API_KEY="your-api-key"
```

Or establish a SAML session:

```shell
cloudsmith auth --owner your-workspace
```

Profiles and explicit configuration files are also supported through
`CLOUDSMITH_PROFILE`, `CLOUDSMITH_CONFIG_FILE`, and
`CLOUDSMITH_CREDENTIALS_FILE`.

## Configure uv

Add the Cloudsmith index to `pyproject.toml`, replacing `OWNER` and
`REPOSITORY`:

```toml
[tool.uv]
keyring-provider = "subprocess"

[[tool.uv.index]]
name = "cloudsmith"
url = "https://dl.cloudsmith.io/basic/OWNER/REPOSITORY/python/simple/"
publish-url = "https://python.cloudsmith.io/OWNER/REPOSITORY/"
```

The provider's Basic Auth username is always `token`. Current versions of uv
can retrieve both fields from keyring without configuring a username. To
support older uv versions, or to make the username explicit, set:

```shell
export UV_INDEX_CLOUDSMITH_USERNAME=token
```

You can enable the provider per invocation instead of in `pyproject.toml`:

```shell
UV_KEYRING_PROVIDER=subprocess uv sync
```

Normal uv operations will now request the password from `keyring` when the
Cloudsmith index requires authentication:

```shell
uv lock
uv sync
uv add your-private-package
```

### Publishing

The same backend can authenticate `uv publish`. Set the non-secret username
when needed and select the configured index:

```shell
export UV_PUBLISH_USERNAME=token
uv publish --index cloudsmith
```

## Custom Domains

Official support is limited to these hosts:

- `dl.cloudsmith.io` for package downloads
- `python.cloudsmith.io` for package publishing

Other `*.cloudsmith.io` and `*.cloudsmith.com` services are deliberately
rejected. This prevents a credential intended for a Python repository from
being returned for an unrelated Cloudsmith service.

For a custom Python repository domain, set `CLOUDSMITH_ORG`. The backend asks
the Cloudsmith API for enabled, validated custom domains with the Python backend
kind and uses the CLI's one-hour domain cache:

```shell
export CLOUDSMITH_ORG=your-workspace
```

## How It Works

uv's subprocess provider invokes one of these commands:

```shell
keyring get SERVICE token
keyring get SERVICE --mode creds
```

`cloudsmith-keyring` is registered through the `keyring.backends` entry-point
group. It recognizes the requested service, resolves a credential through the
Cloudsmith CLI provider chain, and returns it as the Basic Auth password. The
backend does not store, update, or delete credentials.

This mechanism is separate from `uv auth login` and the experimental
`uv auth helper` protocol. It is used by uv package operations when
`keyring-provider = "subprocess"` is enabled.

## Troubleshooting

Test the complete keyring lookup without making an HTTP request:

```shell
keyring get \
  https://dl.cloudsmith.io/basic/OWNER/REPOSITORY/python/simple/ \
  token
```

The command prints the credential on success and exits with status 1 when no
matching credential is available. Avoid running it in logs because its output
is secret.

If uv cannot find `keyring`, ensure the executable installed by `uv tool` is on
`PATH`. If Cloudsmith cannot resolve credentials, verify the active source with:

```shell
cloudsmith whoami --verbose
```

For SAML, the Cloudsmith CLI and keyring subprocess must run as the same OS user
so they can access the same system keyring.

## Development

Install dependencies and run all checks with uv:

```shell
uv sync
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv build
```

The test suite includes direct keyring subprocess tests for both invocation
forms used by uv.

## License

Apache-2.0
