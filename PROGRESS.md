# Progress

| Step | Title | Status | Commit | Date |
|------|-------|--------|--------|------|
| 1 | Project scaffold | ✅ | 78d07e0 | 2026-07-04 |
| 2 | Core schemas & storage | ✅ | ad0388e | 2026-07-04 |
| 3 | Stage-1 hard rules + POLICY.md parser | ✅ | 3bf9136 | 2026-07-04 |
| 4 | Scene engine + inference + policy table | ✅ | 256ded0 | 2026-07-04 |
| 5 | Judge interface + fixture backend + routing | ✅ | 5c814c2 | 2026-07-04 |
| 6 | Demo fixture + replay runner | ✅ | f1da593 | 2026-07-04 |
| 7 | Demo routing regression (full-table) | ✅ | 064ad9e | 2026-07-04 |
| 8 | Real LLM judge backends | ✅(mocked) | c17f42f | 2026-07-04 |
| 9 | Stage-2 embedding classifier | ✅(mocked) | 3bb8384 | 2026-07-04 |
| 10 | Delivery: terminal + desktop | ✅ | 5be3b40 | 2026-07-04 |
| 11 | Delivery: Telegram + feedback buttons | ✅(mocked) | 87bb36a | 2026-07-04 |
| 12 | Learner: signals, EMA, threshold tuning | ✅ | 29e716f | 2026-07-04 |
| 13 | Shadow mode + Tact Report | ✅ | 0dccdbe | 2026-07-04 |
| 14 | Dispatch executors | ✅ | 1ed3796 | 2026-07-04 |
| 15 | Dispatch verification | ✅ | ea5cb7c | 2026-07-04 |
| 16 | Arrive-with-a-plan | ✅ | c8c316f | 2026-07-04 |
| 17 | Memory: curate + associate | ✅(mocked) | 418d883 | 2026-07-04 |
| 18 | Ingest protocol: webhook + MCP | ✅ | ce69874 | 2026-07-04 |
| 19 | Built-in sources: GitHub + RSS | ✅ | 366333c | 2026-07-04 |
| 20 | Onboarding wizard + service install | ✅ | 44da161 | 2026-07-04 |
| 21 | Digest polish + nightly distillation | ✅ | 6000119 | 2026-07-04 |
| 22 | OpenClaw skill | ✅(mocked) | 641a140 | 2026-07-04 |
| 23 | Docs + README | ✅ | 8cafd6d | 2026-07-04 |
| 24 | Release assets | ✅(mocked) | ab916fa | 2026-07-04 |

## Final summary (2026-07-04)

All 24 steps complete, one commit per step, plus four hostile-review commits
(review(phase1..4)). 218 tests + ruff green on every commit; GitHub Actions CI
green on every push. `uvx --from . chief demo` delivers the offline
day-of-engineer replay end-to-end (24 events → 14 blocked · 6 batched ·
3 handled · interrupted exactly once), the full-table routing regression guards
it permanently, and `make release-check` runs the demo from the built v0.1.0
wheel.

Steps marked ✅(mocked) were built against mocks/cassettes because they need
human-only resources — live LLM API keys (8), torch disk space for real
embeddings (9, 17), a Telegram bot token (11), a local OpenClaw install (22),
and PyPI credentials (24). Details and the exact path to un-mock each one are
in BLOCKERS.md. Design decisions taken where the spec was ambiguous are
one-liners in docs/decisions.md (23 ADRs).
