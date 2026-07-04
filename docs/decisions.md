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
