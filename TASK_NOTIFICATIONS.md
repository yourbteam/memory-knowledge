# Task Notifications

A lightweight, git-tracked notification log for long-running / autonomous tasks.

When a background task **completes** (or hits a **blocker** that needs attention), an
entry is appended below and committed + pushed to `main` — so it surfaces as a GitHub
commit you can see from anywhere, without relying on desktop/phone push.

Legend: ✅ success · ⛔ blocked (needs you) · ⏳ in progress

---

## Log

<!-- newest entries on top -->

### ✅ 2026-06-12 — neocurrency-dashboard: REMOTE PG IMPORT COMPLETE

The remote Postgres import **succeeded** — 49,741 rows: entities 20,976 · chunks 10,184 ·
summaries 5,396 · symbols 4,384 · symbol_calls 7,773 · files 1,012 · repo/revision/
branch_head/retrieval_surface. Verified via remote `get_memory_stats`. The import-tool bug
was fixed and deployed (image `neo-import-20260611-223102`, with NUL-strip + dispatcher +
import-repo fixes).

**Remaining (one step):** reproject remote **Qdrant vectors + Neo4j graph** from the
imported PG so semantic retrieval works for this repo. Blocked by the prod safety guard
`ALLOW_REMOTE_REBUILDS=false`; needs a temporary flag toggle (another prod change) →
awaiting your go-ahead in the session.
