# Publishing to PyPI

`agent-chief` is wired for **Trusted Publishing** (OIDC) — no API token lives in
the repo or in your shell history. You do a one-time setup on PyPI, then every
release publishes itself.

## One-time setup (≈3 minutes, needs your PyPI login)

1. Log in at <https://pypi.org> (create the account if needed).
2. Reserve the name by uploading once, **or** pre-register the pending publisher:
   - Go to **Your projects → Publishing → Add a pending publisher** and enter:
     | field | value |
     |---|---|
     | PyPI project name | `agent-chief` |
     | Owner | `SmileLikeYe` |
     | Repository | `agent-chief` |
     | Workflow name | `publish.yml` |
     | Environment | `pypi` |
3. In the GitHub repo: **Settings → Environments → New environment** named
   `pypi` (no secrets needed — OIDC handles auth).

That's it. From now on there is no token to paste.

## Releasing a version

The normal flow is already automated by `release.yml` (builds + attaches
artifacts on a `v*` tag). Publishing then triggers on the **published release**:

```bash
# 1. bump + changelog (the heading format is load-bearing)
#    - pyproject.toml: version = "0.4.0"
#    - CHANGELOG.md:   ## [0.4.0] — <date>
# 2. tag and push
git tag -a v0.4.0 -m "Chief v0.4.0"
git push origin v0.4.0
# → release.yml builds the GitHub Release
# → publish.yml uploads to PyPI when that release is published
```

### Dry-run first (recommended for the very first publish)

Use TestPyPI via the manual trigger to prove the pipeline end-to-end without
touching the real index:

- **Actions → Publish to PyPI → Run workflow → repository: `testpypi`**
- verify: `uvx --index-url https://test.pypi.org/simple/ agent-chief demo`

Then run it again with `repository: pypi`, or just publish the release.

## After the first real publish

- Restore the PyPI badge (removed pre-publish because it rendered "not found"):
  add back to `README.md` / `README.zh-CN.md`, under the CI badge:
  ```
  [![PyPI](https://img.shields.io/pypi/v/agent-chief)](https://pypi.org/project/agent-chief/)
  ```
- Confirm the 60-second promise from a clean machine: `uvx agent-chief demo`.

## Fallback: token-based publish (if you skip Trusted Publishing)

```bash
uv build
UV_PUBLISH_TOKEN=pypi-<your-token> uv publish   # real index
# TestPyPI:
UV_PUBLISH_TOKEN=<token> uv publish --publish-url https://test.pypi.org/legacy/
```
