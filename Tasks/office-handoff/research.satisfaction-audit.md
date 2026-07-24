# research.md — Requirements Satisfaction Audit (Gate 3 of 3)

Depth: will each addressed requirement actually hold end-to-end against the real runtime, files, and
sibling behavior?

## Cycle 1 Assessment

### End-to-End Trace Table
| req | trace | runtime evidence | holds? |
| --- | --- | --- | --- |
| R6 (in sync via shared brain) | client → Azure `/mcp` | `curl /health` → **200** (verified) | yes |
| R5/D6 (`--append-to` into own AGENTS.md) | generate_projections → fenced block | FCSAPI markers at lines 42/243 (verified) | yes |
| R3/R8 (office Claude path rewrite) | configure stamps repo root → hooks load | **5 scripts hardcode `/Users/kamenkamenov/memory-knowledge`** (verified grep) + settings.json hook paths absolute | gap → SGAP-001 |
| R6 (weekly cadence) | launchd → weekly-review.sh → commit + stamp bump | weekly-review.sh commits + bumps DIRECTIVES stamp; CI `weekly-upkeep.yml` also bumps it | gap → SGAP-002 |
| R3 Tier-B venv | `pip install -e .` → hooks import | `import memory_knowledge, mcp` OK (verified) | yes |

### Lens Coverage Matrix (key lenses)
| req | lens | status | evidence |
| --- | --- | --- | --- |
| R3 | config/env dependence | gap | hardcoded paths (SGAP-001) |
| R6 | producer/consumer symmetry | gap | two stamp-bumpers could collide/duplicate (SGAP-002) |
| R5 | cross-feature contract | checked | merge markers idempotent (FCSAPI) |
| R6 | data-reality | checked | brain 200, shared endpoint |
| all | silent-inert | checked | Tier-B fail-open (§1) — degrades, not breaks |

### Blocker Gap Ledger
| gap_id | sev | req | lens | evidence (both sides) | why it breaks | planned fix | closure | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SGAP-001 | blocker | R3,R5,R8 | config/env dependence | Producer: shipped scripts hardcode `/Users/kamenkamenov/memory-knowledge` (5 files verified) + settings.json hook commands are absolute. Consumer: office repo root differs → hooks point at nonexistent paths and silently no-op | Office Claude/Codex would install but inject nothing (silent-inert) | Lock **D10**: `configure.sh` (a) rewrites the repo-root prefix in the 5 scripts to the actual repo root, (b) writes settings.json hook command paths + MCP block + env using that root, (c) sets Codex node PATH per D8 | §5 D10 added | closed |
| SGAP-002 | blocker | R6 | producer/consumer symmetry | Two producers bump the DIRECTIVES "Last reviewed" stamp + can commit: local `weekly-review.sh` (launchd) and CI `weekly-upkeep.yml`. Running launchd on multiple machines → duplicate scheduled commits/integrity runs | Duplicate commits / racing pushes; "in sync" undermined | Lock **D11**: weekly-review launchd is **single-owner** — office does **not** enable it by default (CI `weekly-upkeep.yml` + the existing owner machine cover the cadence); opt-in only, and only one machine owns it | §5 D11 added | closed |

## Cycle 1 Plan
Add D10 (path-stamp mechanism) and D11 (single-owner weekly-review) to §5. Edit research.md only.

## Cycle 1 Edits
§5: added D10 and D11.

## Cycle 2 Assessment (fresh, no edits)
- SGAP-001: D10 makes the path dependency explicit and assigns the rewrite to configure.sh across the
  exact 5-file surface + settings.json — the silent-inert failure is closed at its source.
- SGAP-002: D11 designates a single owner; CI already provides the server-side cadence — no duplicate
  commits by default.
- Post-edit new-gap pass: D10 introduces a configure.sh responsibility the Plan must implement (carried
  forward as a plan requirement, not a research gap). D11 consistent with §1's "CI is informational/
  server-side." No new blockers.

### Final Readiness Proof
| req | satisfied end-to-end? | evidence |
| --- | --- | --- |
| R6 shared brain | yes | /health 200 |
| R5 projection merge | yes | FCSAPI markers |
| R3/R8 path portability | yes (mechanism locked) | D10 + 5-file surface |
| R6 cadence | yes (single-owner) | D11 + CI |
| R3 Tier-B | yes | import OK |

## Final Convergence Check
Fresh no-edit pass, zero blocker satisfaction gaps. **Converged (depth).**
All three research gates converged → research is ready to feed the Plan.
