# Task Notifications

A lightweight, git-tracked notification log for long-running / autonomous tasks.

When a background task **completes** (or hits a **blocker** that needs attention), an
entry is appended below and committed + pushed to `main` — so it surfaces as a GitHub
commit you can see from anywhere, without relying on desktop/phone push.

Legend: ✅ success · ⛔ blocked (needs you) · ⏳ in progress

---

## Log

<!-- newest entries on top -->

### ⛔ 2026-06-11 — neocurrency-dashboard onboarding: BLOCKED, needs your decision

Local side is **done**: clean ingestion completed (10,184 chunks / 5,396 summaries /
4,384 symbols / 1,012 files), exported to JSONL (85.9 MB / 49,741 rows), and the repo is
registered on remote.

**Blocker:** the remote `import_repo_memory_tool` can't onboard a *new* repo — its
repositories insert is a stale 3-column `INSERT … ON CONFLICT`, but post-`016` the
catalog requires `mawf_repository_id`/`status_id` (NOT NULL, no default), which Postgres
checks *before* the conflict resolves → the import errors. I wrote the fix
(`export_import.py` resolves the pre-registered repo) and built a remote image
(`neo-import-20260611-223102`), but **deploying new code to prod was correctly gated** —
it's beyond the "remote import" autonomy and your per-change-approval rule.

**Needs you:** approve the prod deploy of the bundled bug fixes (NUL-strip, dispatcher
retry, import-repo-resolve), or pick the no-deploy client-side-import alternative. Details
in the session.
