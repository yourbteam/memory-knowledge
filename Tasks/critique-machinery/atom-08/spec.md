# Atom 8 — reference declaration and visible no-reference state

Frozen before implementation. The immutable Claude-seat run in `frozen-red/` stopped after seven
of 175 cells: reader 2 returned `revise` for the first benchmark cell, but no reference had been
registered, so the evidence gate refused the judgment and made the remaining 168 cells unreachable.
The three copied files retain the exact matrix, unit manifest, and adjacent refusal log; the source
run is not modified or migrated.

Direction check: the seven-lens matrix and paired benchmark contract remain sound when a real
reference exists. The defect is earlier: `open` permits an operator to postpone whether the
benchmark lens has an evidence source until a seat is already running. Keep that architecture and
move the choice to the immutable opening boundary. This verdict flips only if a run opened with a
real reference cannot preserve Atom 6's existing register-reference and paired-evidence behavior.

Compare two approaches on the same frozen BTM page and payload. `open-terminal-state` requires a
reference id plus page, or a non-empty no-reference reason, and makes no-reference benchmark cells
terminal before any seat is launched. `reader-time-sentinel` keeps accepting undeclared opens and
decides at `read-run`; it can avoid one crash but cannot prove the reason existed at open and allows
the run contract to change later. Rank immutable declaration, zero benchmark reader dispatches,
visible status/document state, legacy-run immutability, and preservation of the declared-reference
contract. Promote only the first approach if the public operator path proves all five.

Green case: open the same delivered page and payload with
`--no-reference "UP supplies no roadmap-shaped benchmark"`. All 25 benchmark cells must be visibly
not applicable with that exact reason, all 150 other cells must remain reachable, `read-run` must
omit the benchmark lens from every seat request, and a completed findings document must print the
benchmark lens as not applicable. No prompt may tell a seat to avoid benchmark defects.
