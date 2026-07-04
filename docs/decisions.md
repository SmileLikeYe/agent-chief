# Architecture Decision Records

One line per decision, per SPEC §7 rule 3.

- 2026-07-04 · Persist models as JSON blobs (`data` column) plus a few key/index columns; add real columns only when queries demand them — simpler than full relational mapping.
- 2026-07-04 · PROGRESS.md commit hashes are backfilled in the following step's commit (hash unknowable before committing).
