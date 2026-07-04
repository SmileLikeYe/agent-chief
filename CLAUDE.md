# CLAUDE.md

Chief — a local-first "chief of staff" that triages everything competing for
the user's attention (agents, heartbeats, CI, RSS) into exactly one of:
interrupt / digest / dispatch / curate / drop. Spec: `SPEC.md` (§ references
throughout the code point there). Build log: `PROGRESS.md`.

## Commands

```bash
make test           # uv run pytest (218 tests, offline, no keys needed)
make lint           # uv run ruff check .
make demo           # offline day-of-engineer replay (deterministic)
make release-check  # lint + test + build wheel + run demo from the wheel via uvx
uv run pytest tests/test_routing.py -k name   # single test
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
- Commit style: `feat(scope): ...` / `fix:` / `docs:` / `review(phaseN): ...`;
  ruff + pytest green on every commit.
