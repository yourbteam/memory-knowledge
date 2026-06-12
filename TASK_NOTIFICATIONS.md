# Task Notifications

A lightweight, git-tracked notification log for long-running / autonomous tasks.

When a background task **completes** (or hits a **blocker** that needs attention), an
entry is appended below and committed + pushed to `main` — so it surfaces as a GitHub
commit you can see from anywhere, without relying on desktop/phone push.

Legend: ✅ success · ⛔ blocked (needs you) · ⏳ in progress

---

## Log

<!-- newest entries on top -->

### ✅ 2026-06-12 — taggable-api: FULLY ONBOARDED TO REMOTE (all 3 stores)

`taggable-api` (branch `main`, commit `6f1ce99`) is now live in all three remote databases:
- **Postgres:** 1,336 chunks · 875 summaries · 556 symbols · 319 files (6,733 rows imported)
- **Qdrant:** 1,336 code_chunks + 875 summary_units (bge-base/768)
- **Neo4j:** Revision 1 · File 319 · Symbol 556

`list_repositories` shows it on `main` @ `6f1ce99` with correct counts. Guard
`ALLOW_REMOTE_REBUILDS` restored to `false`. End-to-end took ~35 min (local ingest ~28 min +
fast remote path: import 6,733 rows → ~6 s Qdrant copy → ~15 s Neo4j rebuild). No code deploy
needed — the import/dispatcher/NUL fixes from the neocurrency run were already live.

### ✅ 2026-06-12 — neocurrency-dashboard: FULLY ONBOARDED TO REMOTE (all 3 stores)

`neocurrency-dashboard` (branch `main`, commit `b1ea8cf`) is now live in all three remote
databases:
- **Postgres:** 10,184 chunks · 5,396 summaries · 4,384 symbols · 1,012 files (49,741 rows imported)
- **Qdrant:** 10,184 code_chunks + 5,396 summary_units (bge-base/768)
- **Neo4j:** graph built (Revision/File/Symbol nodes)

`list_repositories` shows it with the correct latest branch/commit + counts. Guard
`ALLOW_REMOTE_REBUILDS` restored to `false`.

**How (the fast path):** local ingest → export (85.9 MB) → register remote → import to PG
(after fixing+deploying the import tool's post-016 repo bug) → **copied the already-embedded
vectors local→remote Qdrant in ~40s** (instead of a multi-hour webapp re-embed) → Neo4j-only
rebuild (~23s). Bug fixes shipped to prod: NUL-strip, dispatcher retry, import-repo-resolve.

Note: the retrieval *workflow* returns 0 evidence here — but it does the same for known-good
repos (e.g. taggable-server), so it's a pre-existing all-repo behavior, not an onboarding
gap (direct Qdrant search returns correct hits at score 1.0).
