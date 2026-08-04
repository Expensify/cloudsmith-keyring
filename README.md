# cloudsmith-keyring

`cloudsmith-keyring` connects uv's subprocess keyring provider to the
[Cloudsmith CLI](https://github.com/cloudsmith-io/cloudsmith-cli) SAML login
flow. When uv needs credentials for a private Cloudsmith Python repository, the
backend reuses a valid Cloudsmith SSO session or opens the CLI's browser-based
authentication flow and returns the resulting access token.

This is the package's only authentication mechanism. It deliberately does not
return API keys, credentials from `credentials.ini`, or OIDC credentials.

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

Confirm that keyring discovered the backend:

```shell
keyring --list-backends
```

The output should include:

```text
keyrings.cloudsmith.backend.CloudsmithKeyring (priority: 9)
```

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

Set the non-secret Basic Auth username:

```shell
export UV_INDEX_CLOUDSMITH_USERNAME=token
```

Specifying the username also lets uv stream the Cloudsmith CLI's authentication
messages while the browser flow is running. Without it, current uv versions can
still request both credential fields, but buffer keyring's stderr until the
lookup completes.

Normal uv commands can now authenticate automatically:

```shell
uv lock
uv sync
uv add your-private-package
```

The first command that needs credentials opens the Cloudsmith SAML login page in
your browser. After authentication completes, the CLI stores the SSO session in
the system keyring and the original uv command continues.

### Publishing

Use the same non-secret username when publishing:

```shell
export UV_PUBLISH_USERNAME=token
uv publish --index cloudsmith
```

## How It Works

uv's subprocess provider invokes one of these commands:

```shell
keyring get SERVICE token
keyring get SERVICE --mode creds
```

For an official Cloudsmith URL, the backend extracts the workspace from the
path. For example, it infers `expensify` from:

```text
https://dl.cloudsmith.io/basic/expensify/dev/python/simple/
```

The backend then:

1. Asks Cloudsmith's SAML keyring provider for a valid access token, including
   its normal refresh behavior.
2. Runs the equivalent of the following command when no usable token exists:

   ```shell
   python -m cloudsmith_cli auth --owner expensify
   ```

3. Routes all interactive CLI output to stderr so keyring's stdout remains a
   valid credential response.
4. Resolves the newly stored SAML token and returns it as the Basic Auth
   password for username `token`.

The CLI process uses the same Python environment as the keyring backend. When uv
provides no stdin to its helper, the backend opens the controlling terminal so
Cloudsmith can still request a 2FA code.

An existing valid SAML session is reused without reopening the browser.

## Custom Domains

Official support covers:

- `dl.cloudsmith.io` for package downloads
- `python.cloudsmith.io` for package publishing

Other `*.cloudsmith.io` and `*.cloudsmith.com` services are rejected.

For a custom Python repository domain, provide the workspace because it cannot
be inferred from the URL:

```shell
export CLOUDSMITH_ORG=your-workspace
```

The backend authenticates that workspace through the same CLI SAML flow, then
uses the Cloudsmith API to verify that the requested host is an enabled,
validated Python custom domain before returning the token.

## Local Testing

Install the project dependencies and verify backend discovery:

```shell
uv sync
uv run keyring --list-backends
```

Then test the complete interactive flow:

```shell
uv run keyring get \
  "https://dl.cloudsmith.io/basic/OWNER/REPOSITORY/python/simple/" \
  token
```

If there is no valid SAML session, this command opens the Cloudsmith login page.
It prints the access token after authentication, so do not run it in logs.

To exercise uv itself, make the development keyring executable available and
install a private package:

```shell
export PATH="$PWD/.venv/bin:$PATH"

uv pip install \
  --keyring-provider subprocess \
  --index-url \
  "https://token@dl.cloudsmith.io/basic/OWNER/REPOSITORY/python/simple/" \
  YOUR_PRIVATE_PACKAGE
```

## Development

Run all checks with:

```shell
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv build
```

The tests verify token reuse, browser-auth fallback, owner inference, custom
domain validation, terminal handling, and clean subprocess output. They mock the
browser flow and never require live Cloudsmith credentials.

## License

Apache-2.0
