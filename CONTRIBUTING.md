# Contributing to Chief

Thanks for your interest! Chief is small on purpose — the whole brain fits in
your head after an afternoon of reading. This document gets you productive in
five minutes.

## Dev setup

```bash
git clone https://github.com/SmileLikeYe/agent-chief && cd agent-chief
uv sync --dev          # Python 3.12+, https://docs.astral.sh/uv/
make test lint         # 218 tests + ruff, fully offline — no keys needed
make demo              # the offline day-of-engineer replay
```

The test suite needs **no network, no API keys, and no real `~/.chief`** —
tests point `CHIEF_HOME` at a tmpdir and use the deterministic `fixtures`
judge. If your change needs a key to test, it's designed wrong; add a cassette
(see `judge/fixtures.py` and the httpx MockTransport tests).

## The rules of the house

1. **Tests first.** Every behavior change lands with the test that pins it.
   The demo routing table (`tests/test_demo_routing.py`) is a full-table
   regression — if your change legitimately re-routes a demo event, update the
   fixture table deliberately and say why in the PR; never loosen the test.
2. **`SPEC.md §13` is a hard no.** No arbitrary shell execution (the shell
   executor is a query-only argv whitelist — never `shell=True`), no
   mic/screen/geofencing, no web UI, no cloud sync, no telemetry.
3. **Ambiguity → simpler option + a one-line ADR** in
   [`docs/decisions.md`](docs/decisions.md).
4. **Keep the core dependency-light.** Embeddings default to the
   dependency-free `HashEmbedder`; heavyweight deps go behind optional extras.
5. **Green on every commit**: `make lint test` must pass.

## Commit style

```
feat(scope): add per-topic dispatch propensity
fix: telegram poller surfaces HTTP errors
docs: clarify quiet-hours semantics
```

## Pull requests

- One logical change per PR; small is beautiful.
- Explain *why* in the description; the diff explains *what*.
- CI (ruff + pytest on 3.12) must be green.

## Good first areas

- New **scene providers** (`context/providers/`) — e.g. OS focus/lock state.
- New **judge backends** (`judge/`) — subclass the HTTP judge, ~40 lines.
- New **ingest sources** (`ingest/sources/`) — subclass `Poller`, ~60 lines.
- New **delivery channels** (`delivery/`) — but check `ROADMAP.md` first;
  Slack/Discord/WeChat are deliberately v2.

## Questions

Open a [discussion or issue](https://github.com/SmileLikeYe/agent-chief/issues)
— unpolished questions welcome.
