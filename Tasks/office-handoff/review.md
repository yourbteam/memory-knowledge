# Office Handoff — Review (Review Playbook)

Baseline = `plan.md` (both plan gates green). RV2 = cover the plan; RV1 = real findings only.

## RV2 — Plan coverage (every plan item → built + verified)
| Plan item | Built | Verified |
| --- | --- | --- |
| D1.1 folder tree | yes | `find` tree = 31 files, matches |
| D1.2 payload 24 files (excl. spark-candidates, __pycache__) | yes | count 24; spark-candidates absent |
| D1.3 claude-settings.hooks.json (3 UPS + Stop + env + mcp, `__REPO_ROOT__`) | yes | sandbox checks 1–7 |
| D1.4 codex-config.snippet.toml (`__REPO_ROOT__`,`__NODE_DIR__`) | yes | sandbox checks 10,12 |
| D1.5 configure.sh: roots, path-stamp, deep-merge, toml guard, skill, projections, venv, flags | yes | `bash -n` OK; sandbox checks 1–15 |
| D2 INSTALL.md (§0–9, 3 targets, usage+verify+sync+rollback) | yes | read-through; sections present |
| D3 MANIFEST.md (commit 4f0d3c4, date, file list) | yes | present |
| D4 local Codex wiring (8 repos) | yes | all 8 `Prime directive` ×1 |
| Build acceptance (syntax, secrets, json merge, markers, INSTALL coverage) | yes | secrets clean; merge idempotent |

## RV2 — User-requirement coverage
| Requirement | Met by | Evidence |
| --- | --- | --- |
| Standalone folder, all files | `~/Downloads/working-agreement-handoff/` | 31-file tree, 188K, self-contained |
| Separate install document | `INSTALL.md` (+ MANIFEST) | consolidated, 3 targets |
| Office Claude (separately) | INSTALL §3 + `configure.sh --claude` | sandbox merge non-destructive |
| Office Codex (separately) | INSTALL §4 + `configure.sh --codex` | sandbox MCP+skill+projection |
| Local Codex (this machine) | Deliverable 4 executed | 8/8 repos ×1 directive |
| All wired and in sync | INSTALL §0/§7 (git + Azure + projections) | brain /health 200; one source of truth |

## RV1 — Findings
**Must-fix:** none open.
- **SGAP-003 (found & fixed in build):** stale pure-projection AGENTS.md were being duplicated by
  `--append-to`; fixed with first-line detection → `--write`. Verified live (8/8 repos ×1) and in the
  sandbox (check 15: stale overwritten ×1, hand-authored merged ×1 with own content kept).

**Nits (optional, not blocking):**
- **N1 — `--venv` hardcodes `python3.12`.** INSTALL states "≥3.12" but configure looks for the exact
  `python3.12` binary; a machine with only `python3.13` would hit the warn+manual path. Harmless
  (prints the manual command) but could fall back to `python3` after a version check. Offered, not applied.
- **N2 — projection repo list is a literal default in configure.sh.** Editable via
  `MK_PROJECTION_REPOS` and documented; fine for the canonical set, user edits per machine (D5).

## Verdict
Full coverage confirmed. The bundle installs both clients on a fresh machine non-destructively and
idempotently (sandbox-proven end-to-end), local Codex is in sync (8/8), and all three targets share
the same source-of-truth + brain. No must-fix findings.
