# Architecture Decision Records

One line per decision, per SPEC §7 rule 3.

- 2026-07-04 · Persist models as JSON blobs (`data` column) plus a few key/index columns; add real columns only when queries demand them — simpler than full relational mapping.
- 2026-07-04 · PROGRESS.md commit hashes are backfilled in the following step's commit (hash unknowable before committing).
- 2026-07-04 · POLICY.md grammar kept tiny: `- topic` under "Muted topics", `- <glob> -> <route>` under "Rules"; "Learned" section is prose, never parsed for routing.
- 2026-07-04 · Embeddings are pluggable (`core/embedding.py` Protocol); default is a dependency-free hashed bag-of-words vectorizer, real sentence-transformers model wired at Step 9.
- 2026-07-04 · POLICY parser lives in `core/policy.py` (the `policy/` dir holds only user-facing templates per §6).
- 2026-07-04 · Stage-1 rules evaluated in exact SPEC order: quiet hours → muted → dedup → zero-info → policy rules.
