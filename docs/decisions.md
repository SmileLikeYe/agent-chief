# Architecture Decision Records

One line per decision, per SPEC §7 rule 3.

- 2026-07-04 · Persist models as JSON blobs (`data` column) plus a few key/index columns; add real columns only when queries demand them — simpler than full relational mapping.
- 2026-07-04 · PROGRESS.md commit hashes are backfilled in the following step's commit (hash unknowable before committing).
- 2026-07-04 · POLICY.md grammar kept tiny: `- topic` under "Muted topics", `- <glob> -> <route>` under "Rules"; "Learned" section is prose, never parsed for routing.
- 2026-07-04 · Embeddings are pluggable (`core/embedding.py` Protocol); default is a dependency-free hashed bag-of-words vectorizer, real sentence-transformers model wired at Step 9.
- 2026-07-04 · POLICY parser lives in `core/policy.py` (the `policy/` dir holds only user-facing templates per §6).
- 2026-07-04 · Stage-1 rules evaluated in exact SPEC order: quiet hours → muted → dedup → zero-info → policy rules.
- 2026-07-04 · Delivery levels ordered terminal < desktop < silent < vibrate < ring; policy-table "silent push"=silent, "ring"=ring.
- 2026-07-04 · Calendar provider uses a minimal built-in ICS parser (DTSTART/DTEND/SUMMARY); no gcal API in v1 core.
- 2026-07-04 · Scene-threshold overrides live under a "## Scene thresholds" POLICY.md section, `- <scene> = <float>`.
- 2026-07-04 · scene_cost defaults to 0.0 (scene tolerance already lives in per-scene interrupt thresholds); the cost term stays in the formula and Decision for auditability, configurable later.
- 2026-07-04 · Default topic weights: 0.2 per dimension (score = mean of the 5 components).
- 2026-07-04 · dispatchable && route∈{interrupt,digest} sets route="dispatch"; delivery still happens after the task completes (SPEC §4.4 arrive-with-a-plan).
- 2026-07-04 · Stage-1 drop rules (muted/dedup/zero-info) now run BEFORE the quiet-hours digest rule — §4.7 events 1/24 prove noise must die at night too, not resurface in the morning digest.
- 2026-07-04 · "Interrupted exactly once" counts interrupt-level deliveries (user decision requested, demo #16); a post-dispatch silent FYI (#9) counts as handled, not an interruption.
- 2026-07-04 · Demo digest pool flushes at fixture-marked digest moments (morning at #3, evening at #20); items after 18:30 wait for the next digest.
- 2026-07-04 · §12 name check: agent-chief, chiefd, cortexd all free on PyPI (404); kept `agent-chief` to match the existing repo/remote.
- 2026-07-04 · review(phase1): demo anchor #3 moved to 08:00 exactly; morning digest now carries 4 overnight items; event #2 rewritten as a pre-8am zero-info drop to keep the timeline monotonic.
- 2026-07-04 · Judge prompt sent as system+system+user messages (stable system / daily context / per-call user) to maximize provider prompt caching; DeepSeek adapter subclasses the OpenAI adapter (API-compatible).
- 2026-07-04 · Judge backend factory lives in judge/factory.py; "fixtures" is a selectable backend so the demo path needs no special-casing.
- 2026-07-04 · sentence-transformers is an optional extra (`uv sync --extra embeddings`) so `uvx chief demo` stays torch-free (<60s wow, Principle 1); make_embedder() degrades to HashEmbedder with a warning.
- 2026-07-04 · Stage-2 "route by historical same-class mean" = majority route among engaged records above 0.88 similarity, nearest-first tie-break.
- 2026-07-04 · engaged-similar beats dismissed-similar when both fire (spec: drop only "with no engaged record").
