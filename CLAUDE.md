# CLAUDE.md

Chief — a local-first "chief of staff" that triages everything competing for
the user's attention (agents, heartbeats, CI, RSS) into exactly one of:
interrupt / digest / dispatch / curate / drop. Spec: `SPEC.md` (§ references
throughout the code point there). Build log: `PROGRESS.md`.

## Commands

```bash
make test           # uv run pytest (301 tests, offline, no keys needed)
make lint           # uv run ruff check .
make demo           # offline day-of-engineer replay (deterministic)
make readme-metrics # regenerate the quantified README first screen
make release-check  # lint + test + build wheel + run demo from the wheel via uvx
uv run pytest tests/test_routing.py -k name   # single test
uv run chief eval   # regression (demo 24, must be 100%) + capability (golden 200)
uv run chief trace <event_id>   # replay one decision chain with costs
uv run chief lite '<event json>'  # zero-daemon judgment (skills use this)
uv run chief ui                   # local web console at 127.0.0.1:8787/ui
uv run chief connect composio --secret …   # + github / rss; chief sources
```

Everything runs through `uv`. Python 3.12. No network, no API keys, and no
real `~/.chief` are needed for the test suite — tests set `CHIEF_HOME` to a
tmpdir and use the `fixtures` judge backend.

## Architecture (one paragraph)

`ingest/` normalizes payloads (webhook :8787, MCP tools, GitHub/RSS pollers) →
`core/brain.py::Brain.process` runs the pipeline: triage-merge → stage-1 hard
rules (`core/scorer.py::stage1`) → stage-2 similarity classifier → memory
associate → LLM judge (`judge/`, pluggable via `judge/factory.py`) →
`score_and_route` (score = Σ w_topic·component, per-scene thresholds from
`context/infer.py::SCENE_POLICY`) → persist to SQLite (`core/state.py`, all
tables use a JSON `data` blob column) → fire-and-forget actor
(`cli/runtime.py::make_actor`) delivers or dispatches. Dispatch always
"arrives with a plan": executor runs first, result is verified
(`dispatch/acceptance.py` — "done is a claim, not a proof"), then delivery.
Learning: `core/learner.py` (EMA topic weights, shadow mode, nightly
threshold tuning at 03:00 via the scheduler in `cli/runtime.py`).
v3.1 additions: `eval/` (golden 200-case dataset + agreement harness),
`Decision.trace` (per-stage latency/tokens/USD via `judge/pricing.py`),
versioned prompts (`judge/templates/<v>/*.j2`), and judge-failure degradation
(rules-only conservative routing, `degraded=true`, auto-recovery).

## Conventions

- Tests first: each `tests/test_*.py` encodes the SPEC §9 acceptance criteria
  for its step. The demo routing table is a full-table regression
  (`tests/test_demo_routing.py`) — if you change routing behavior on purpose,
  update the fixture table deliberately, never loosen the test.
- Ambiguity in the spec → pick the simpler option and add a one-line ADR to
  `docs/decisions.md`.
- `SPEC.md §13` is a hard forbidden list: no arbitrary shell execution
  (`dispatch/executor.py` shell templates are a query-only argv whitelist —
  keep it that way, never `shell=True`), no mic/screen/geofencing, no web UI,
  no cloud sync, no Slack/Discord/WeChat delivery.
- Embeddings default to the dependency-free `HashEmbedder`
  (`core/embedding.py`); sentence-transformers is an optional extra
  (`--extra embeddings`) — never make it a hard import.
- Human-only resources (LLM keys, Telegram token, PyPI creds) are mocked;
  status and un-mock instructions live in `BLOCKERS.md`.
- Prompts are versioned template dirs; no prompt change without a
  `chief eval --compare` diff report (CONTRIBUTING.md).
- Release flow: bump pyproject version + add a CHANGELOG.md entry + push a
  `v*` tag; workflows do the rest. The `## [x.y.z]` changelog heading format
  is load-bearing — release.yml and sync-release-notes.yml parse it.
- Commit style: `feat(scope): ...` / `fix:` / `docs:` / `review(phaseN): ...`;
  ruff + pytest green on every commit.
