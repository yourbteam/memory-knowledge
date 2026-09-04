# Atom 9 — declared upstream material and atomic cell recording

Frozen before implementation. The immutable v2 Claude run in `frozen-red/` opened with 25
benchmark cells not applicable and six registered producer sources. Both seats returned all 150
applicable judgments, but recording stopped on the first upstream defect claim because the seats
had never received producer material. The stop left five sibling cells holding reader 1 only,
145 cells unjudged, and zero cells judged.

Direction check: the fixed matrix and evidence gates remain sound. Atom 8 moved the goal by making
the benchmark source choice terminal at open; this run reached the next, symmetric declaration
boundary. The new half-recording defect is caused by treating a multi-cell reducer as one
transaction. Keep the approach and make the upstream source choice immutable at open, expose
producer text to the upstream lens, require a named exact source passage for each defect claim,
and commit both seats for one cell in one write. This verdict flips only if source-visible,
cell-atomic replay still leaves any applicable cell unrecorded or any grounded upstream defect
without exact registered-source words.

Compare `source-cited-cell-transaction` with `prompt-only-whole-batch` on the same frozen v2
manifest, registry, matrix, and 50 captured seat responses. Rank open-time declaration, exact
producer grounding, complete sibling recording, visible per-cell refusal, and zero model calls.
The second approach is the recorded control: it exited on the first ungrounded upstream claim and
left five one-seat siblings. Promote the first only if it consumes all captured responses,
records every applicable cell, leaves no one-seat cell, preserves ungrounded claims as visible
refusals, and changes none of the frozen red bytes.

The public `open` contract requires exactly one upstream mode: one or more repeated
`--upstream-source <id>=<state.json#key>` declarations, or
`--no-upstream "<recorded reason>"`. No-upstream marks all 25 upstream cells not applicable,
never asks that lens, and prints the reason in status and the findings document. With registered
sources, seats receive numbered material from the immutable registry. Reject/revise under
`upstream-trace` requires a registered source id and exact source line span.

`read-cell` and `read-run` collect both seat claims before one cell write. If either claim
cannot be recorded, the cell stores both claims plus an actionable refusal and processing
continues. A recording refusal is terminal and visible but is not a defect verdict. A genuine
reader disagreement remains an owner question, and every such question contains both seats.
