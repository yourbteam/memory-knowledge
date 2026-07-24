# plan.md — Requirements Coverage Audit (Plan Gate A)

## Cycle 1 Assessment

### Requirement Inventory (carried from research R1–R12 + plan-specific)
| req_id | requirement | type |
| --- | --- | --- |
| R1 standalone folder w/ all files | explicit |
| R2 consolidated INSTALL doc | explicit |
| R3 office Claude (separately) | explicit |
| R4 office Codex (separately) | explicit |
| R5 local Codex wiring | explicit |
| R6 in sync | explicit |
| R7 usage/benefit per upgrade | explicit |
| R12 per-target verification | implied |
| P1 fresh machine (no existing settings.json/config.toml) | implied/negative |
| P2 idempotent re-run | implied |
| P3 secrets hygiene | non-functional |

### Coverage Matrix
| req | status | where |
| --- | --- | --- |
| R1 | addressed | §1.1 tree, §1.2 list |
| R2 | addressed | Deliverable 2 (INSTALL sections 0–9) |
| R3 | addressed | INSTALL §3 + configure steps 2,3,7 |
| R4 | addressed | INSTALL §4 + configure steps 4,5,6 |
| R5 | addressed | Deliverable 4 + INSTALL §5 |
| R6 | addressed | INSTALL §0,§7 |
| R7 | addressed | INSTALL §3–5 "what each does/benefit" |
| R12 | addressed | INSTALL §6 + build Verification |
| P1 | **partial → CGAP-001** | configure "merge into ~/.claude/settings.json" assumes file exists; fresh machine has none |
| P2 | addressed | §1.5 idempotent (json merge replaces same keys; grep guard on toml) |
| P3 | addressed | build Verification grep for secrets |
| R3/R4 "separately" | **partial → CGAP-002** | configure.sh does both targets at once; no way to install just one |

### Blocker Gap Ledger
| gap_id | sev | req | evidence | planned fix | closure | status |
| --- | --- | --- | --- | --- | --- | --- |
| CGAP-001 | blocker | P1 | §1.5 step 3/4 assume `~/.claude/settings.json` + `~/.codex/config.toml` exist | configure.sh **creates** a minimal file if absent (settings.json `{}` then merge; config.toml touch then append) | §1.5 steps 3,4 amended | closed |
| CGAP-002 | blocker | R3,R4 ("separately") | configure runs all steps; user may want one client only | Add `--claude` / `--codex` selective flags (default both); INSTALL §3/§4 already standalone-manual | §1.5 args amended | closed |

## Cycle 1 Plan
Amend §1.5: handle missing config files (CGAP-001); add `--claude`/`--codex` flags (CGAP-002).

## Cycle 1 Edits
Applied to plan.md §1.5 (args + steps 3,4).

## Cycle 2 Assessment (fresh, no edits)
All requirements addressed; P1 (fresh machine) and "separately" now covered. Post-edit new-gap pass:
selective flags don't conflict with idempotency; create-if-absent preserves the merge-not-clobber rule.
No orphan mechanisms; no silent drops.

### Final Coverage Proof
| req | covered? | acceptance |
| --- | --- | --- |
| R1–R7,R12,P1–P3 | yes | §1.1/1.2/1.5, Deliverables 2 & 4, INSTALL §0–9 |

## Final Convergence Check
Fresh no-edit pass, zero blockers. **Converged (breadth).**
