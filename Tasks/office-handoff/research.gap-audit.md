# research.md — Doc Gap Closure Audit (Gate 1 of 3)

Target: `Tasks/office-handoff/research.md`. Question: is it self-sufficient, internally
consistent, and are its cited claims real — enough for a Plan to build from one-shot?

## Cycle 1 Assessment

### Section Inventory
| unit_id | section | type | relevance |
| --- | --- | --- | --- |
| U1 | Goal/intent | intro | high |
| U2 | §1 payload table + dependency tiers | table | high |
| U3 | §2 reference wiring (2a/2b/2c) | tables | high |
| U4 | §3 sync model | prose | high |
| U5 | §4 deliverable layout | schema | high |
| U6 | §5 locked decisions | locked-list | high |
| U7 | §6 open questions | prose | med |
| U8 | §7 evidence index | list | med |

### Coverage Matrix (lenses × units)
| unit | decision-completeness | repo-grounding | edge/failure | contradictions | result |
| --- | --- | --- | --- | --- | --- |
| U2 | gap (GAP-001) | checked (paths cited) | checked (fail-open noted) | none | gap |
| U3 | gap (GAP-002) | checked (settings/config verified) | n/a | none | gap |
| U4 | checked | n/a | n/a | none | checked |
| U5 | gap (GAP-003) | checked | checked | none | gap |
| U6 | checked (D2 neutralizes) | n/a | n/a | none | checked |
| others | checked | checked | n/a | none | checked |

### Blocker Gap Ledger
| gap_id | sev | unit | lens | evidence | why blocker | planned fix | closure | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAP-001 | blocker | U2 | decision-completeness | research names Tier-B `.venv` but no bootstrap command/Python version; `pyproject.toml:9` requires-python ≥3.12, deps include `mcp>=1.26` (verified import OK) | Plan cannot specify the office venv step | Add Tier-B bootstrap: `python3.12 -m venv .venv && .venv/bin/pip install -e .`; state ≥3.12 prereq | §1 amended | closed |
| GAP-002 | blocker | U3 | decision-completeness | `~/.codex/config.toml` `[mcp_servers.memory-knowledge].env.PATH` hardcodes `/Users/kamenkamenov/.nvm/versions/node/v24.9.0/bin`; office node path will differ | Codex MCP block would point at a nonexistent node path on office | Add D8: codex snippet parametrizes node dir (`$(dirname "$(command -v npx)")`); requires node/npx prereq | §5 D8 added | closed |
| GAP-003 | blocker | U5 | decision-completeness | This machine demoted `CLAUDE.md` to generated pointers (`generate_projections.py --kind claude-pointer`); research silent on whether office must match for "in sync" | Ambiguous whether office needs pointer demotion | Add D9: Claude directives arrive via the hook regardless of CLAUDE.md; pointer demotion is optional/cosmetic — skip by default on office | §5 D9 added | closed |

### Cleanup List
| item | unit | issue |
| --- | --- | --- |
| C1 | U2 | weekly-upkeep.yml/upkeep-heartbeat.yml are repo CI needing GitHub secrets — already pushed server-side; not per-machine. Mark explicitly "informational, no machine action" (done in §1). |

## Cycle 1 Plan
Apply GAP-001 (§1 Tier-B bootstrap), GAP-002 (§5 D8), GAP-003 (§5 D9). Edit research.md only.

## Cycle 1 Edits
- §1: added Tier-B venv bootstrap line + Python ≥3.12 prerequisite.
- §5: added D8 (node-path-portable Codex snippet) and D9 (pointer demotion optional).

## Cycle 2 Assessment (fresh, post-edit, no further edits)
Re-read all 8 units against all lenses:
- U2: Tier-B now has a concrete bootstrap command + version prereq → decision-complete.
- U3: D8 resolves the node-path portability → no ungrounded portability claim.
- U5: D9 resolves the pointer-demotion ambiguity.
- Post-edit new-gap pass: D8 introduces a node prereq — consistent with §1 "Codex MCP needs node/npx"; no new contradiction. D9 consistent with §2a (hook delivers directives). No new blockers.
- Contradiction sweep: sync model (§3) ↔ decisions (§5) ↔ deliverable (§4) consistent.

### Final Readiness Proof
| category | status | evidence |
| --- | --- | --- |
| runtime entry points / wiring | ready | §2a/2b verified against settings.json + config.toml |
| dependency model | ready | §1 Tier A/B + bootstrap; pyproject:9-20 |
| sync model | ready | §3 (git + Azure + projections), HEAD 4f0d3c4 |
| portability | ready | D2 (paths), D8 (node) |
| decisions locked | ready | §5 D1–D9 |
| out-of-scope | ready | CI is informational (C1) |

## Final Convergence Check
Cycle 2 is a no-edit fresh full pass with zero open blockers. **Converged (internal readiness).**
Scope caveat: this gate proves the document is self-sufficient and its cited claims are real; it does
**not** prove breadth (coverage gate) or end-to-end satisfaction (satisfaction gate) — run next.
