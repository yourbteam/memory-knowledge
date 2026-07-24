# plan.md — Requirements Satisfaction Audit (Plan Gate B)

Depth: will each addressed step actually hold against the real scripts/runtime?

## Cycle 1 Assessment

### End-to-End Trace Table
| req | trace | evidence | holds? |
| --- | --- | --- | --- |
| projection portability | configure step 6 → generate_projections (no --directives) | `generate_projections.py:31` `DEFAULT_DIRECTIVES = Path(__file__).resolve().parent/"DIRECTIVES.md"` — co-located, portable (verified) | yes |
| `--append-to` idempotency | re-run replaces fenced block only | markers at FCSAPI 42/243 (verified earlier) | yes |
| standalone w/o clone (Tier A) | REPO_ROOT → hooks → inject | hooks ref `$REPO_ROOT/working-agreement/*`; payload has those + DIRECTIVES.md, but **no pyproject** | gap → SGAP-001 |
| settings.json merge | configure step 3 → json merge | settings.json `hooks.UserPromptSubmit` is an **array**; shallow overwrite would drop a user's existing hooks | gap → SGAP-002 |
| Codex MCP | snippet → mcp-remote-wrapper → npx | wrapper needs node; D8 sets NODE_DIR | yes (D8) |

### Blocker Gap Ledger
| gap_id | sev | req | lens | evidence (both sides) | why it breaks | planned fix | closure | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SGAP-001 | blocker | R1 (standalone, no clone) | scope-vs-usage | configure assumes REPO_ROOT = cloned repo; the handoff `payload/` has the scripts + DIRECTIVES.md (Tier A works) but no `pyproject` (Tier B can't) | A user who only copies the folder (no git) needs Tier-A wiring to still work; undocumented REPO_ROOT=payload path | Lock: REPO_ROOT may be **the cloned repo (Tier A+B)** or **the handoff `payload/` dir (Tier A only)**; `--venv` detects `pyproject.toml` and warns+skips if absent | §1.5 step 1,7 amended | closed |
| SGAP-002 | blocker | P1/P2 | producer/consumer symmetry | Producer: configure writes `hooks`. Consumer: Claude reads `hooks.UserPromptSubmit` as a list; an existing office config may already have entries. A shallow key overwrite would **delete** them | Could wipe a user's pre-existing hooks; non-idempotent on re-run (duplicates) | Lock: python merge **deep-merges the hook arrays** — append our hook entries only if the same `command` path is not already present (idempotent); same for `mcpServers` (set our key, keep others) | §1.5 step 3 amended | closed |

## Cycle 1 Plan
Amend §1.5 step 1/7 (REPO_ROOT = clone or payload; venv guard) and step 3 (deep-merge + idempotent append).

## Cycle 1 Edits
Applied to plan.md §1.5.

## Cycle 2 Assessment (fresh, no edits)
- SGAP-001: REPO_ROOT dual-mode documented; Tier-A-only path is explicit and matches the fail-open tier model (research §1).
- SGAP-002: deep-merge + presence-guarded append makes the wiring non-destructive and idempotent; matches D-decisions (merge-not-replace).
- Post-edit new-gap pass: dual REPO_ROOT doesn't conflict with path-stamping (step 2 rewrites whichever root's scripts). Deep-merge doesn't conflict with create-if-absent (CGAP-001). No new blockers.

### Final Readiness Proof
| req | satisfied end-to-end? | evidence |
| --- | --- | --- |
| projection portability | yes | generate_projections.py:31 |
| standalone Tier A no-clone | yes | SGAP-001 fix |
| non-destructive wiring | yes | SGAP-002 deep-merge |
| Codex MCP node path | yes | D8/NODE_DIR |
| local-codex projections | yes | Deliverable 4 + --append-to verified |

## Final Convergence Check
Fresh no-edit pass, zero blocker satisfaction gaps. **Converged (depth).**
Plan is build-ready (both plan gates green).

---

## Build-phase addendum — SGAP-003 (found during execution, WC1 verify)
| gap_id | sev | req | lens | evidence (both sides) | why it breaks | fix | closure | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SGAP-003 | blocker | R5 (local Codex), office Codex | producer/consumer symmetry / data-reality | The depth gate assumed "repo has its own AGENTS.md ⇒ hand-authored." **Reality (verified `head -1` + `grep -c "Prime directive"`):** 4 trusted repos (taggable-api, taggable-database, united-partners, agentic-trading) had AGENTS.md that were **stale pure `--write` projections** (line 1 = generated header). `--append-to` appended a *second* full directive copy → "Prime directive" appeared **2×** in each. | Codex would load directives twice (bloat, and two different "Last reviewed" stamps) | Detect a pure-projection file (first line contains `GENERATED from working-agreement`) → use `--write` (overwrite); only `--append-to` into a hand-authored file. Applied to: `configure.sh` step 6, INSTALL.md §5 loop, plan step 6 + Deliverable 4. | All 8 repos now show `Prime directive` ×1 (verified); configure.sh re-parses `bash -n` OK | closed |

This is the canonical satisfaction-gap class (un-cited data reality vs the document's assumption) —
caught at build because WC1 required verifying the actual file contents, not just marker counts.
