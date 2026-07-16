# Comparative Evaluation Contract (Historical Promotion Evidence)

## Blind Fixtures

Use six hidden cases spanning:

- current-runtime codebase behavior;
- future-system design;
- mixed maturity that must be split;
- unavailable runtime evidence;
- conflicting requirements;
- a scope-inflation trap.

Each case stores raw request, evidence, and an answer-free output contract separately from structured gold predicates. The public contract declares allowed scope and maturity identifiers, claim questions, candidate material-gap identifiers, and planner obligations. It never contains expected values, required evidence, criticality, or the correct material-gap selection. Stage only these raw files into agent-visible temporary directories. Never put gold paths, expected findings, suspected defects, or prior conclusions in an agent prompt or snapshot.

## Canonical Corpus And Bounded Matrix

The canonical corpus remains all six fixtures. `prepare` always validates the manifest,
directory shape, public contract, evidence, and hidden gold for every canonical fixture.
With no case selection, it locks the full matrix:

- 6 legacy research executions using the current `research-playbook` and its three gates;
- 6 candidate research executions using the isolated candidate tree;
- 6 fresh-planner executions using only the corresponding v2 handoff.

This is 18 top-level executions. Internal v2 subagents remain subject to the skill's shared budget and lifecycle evidence requirements. Record skill-tree hashes for both research arms before execution.

For bounded convergence validation, select exactly these three sentinel cases with repeated
`--case-id` arguments:

- `current-runtime`, proving critical material-gap preservation and a practical planner handoff;
- `mixed-maturity`, proving current and future behavior remain separated without demands for
  nonexistent runtime evidence;
- `scope-inflation-trap`, proving neither research nor planning invents requirements.

This profile locks 9 top-level executions: legacy research, v2 research, and a fresh v2-package-only
planner for each sentinel. It uses the same fixtures, output contracts, hashes, scorer, thresholds,
agent independence requirements, and lifecycle checks as the full matrix. Case selection only
reduces live executions; it does not create a smaller fixture corpus or weaken a predicate. The
replacement approval followed this comparison; this file now preserves its evidence contract only.

## Deterministic Evidence

For every execution retain case ID, arm, role, runtime-agent ID, input-envelope hash, output hash, start and end time, attempt use, and slot-close evidence. Record each v2 research result as its exact six-file package directory and use the canonical package-tree hash as both the research output hash and the fresh planner's input hash. The planner consumes that recorded directory, never an evaluator-only summary JSON. Reject duplicate execution tuples, reused runtime-agent IDs, mismatched input hashes, incomplete matrices, outputs recorded before slot closure, package-file additions or omissions, and package artifact-hash mismatches.

Score only named structured predicates declared in the public contract. A planner must provide non-empty implementation and verification steps for every declared obligation; self-reported pass booleans without those steps do not count. Do not use a model judge or free-form similarity score.
A v2 package may retain true planner-owned material gaps while all three lenses return `PASS`; blind evaluation must verify that those gaps preserve the exact public candidate IDs and survive adjudication as non-blocking planner handoffs.

## Exact Output Envelopes

The prepared matrix declares and locks the output contract for every role. `record`
validates the contract before copying an output into its immutable destination, and
`score` validates the same declaration again.

- Legacy research JSON has exactly `schema_version`, `claims`, and `material_gaps`.
- V2 research is the exact six-file package.
- V2 planner JSON has exactly `schema_version`, `claims`, `material_gaps`, and
  `planner`. It transcribes claims and material gaps from the recorded package, then
  adds the plan assessment. The planner object has exactly `verdict`, `checks`,
  `obligations`, `questions`, and `unresolved_choices`.

Reject malformed outputs at `record`; never retain an output that the scorer cannot
consume.

## Locked Promotion Thresholds

Promotion requires all of these:

- zero invented evidence across v2 research and planner outputs;
- zero scope or maturity drift;
- 100 percent recall of critical gold predicates;
- no more false material gaps than the legacy arm;
- every v2 run remains within 3 rounds, 15 attempts, and 60 minutes;
- all three lens roles and adjudication have independent lifecycle evidence;
- every fresh planner passes the one-shot planner rubric;
- a fresh canonical invocation selects `research-playbook`;
- canonical routing metadata permits the governed research entry point;
- every unrelated managed Codex skill remains byte-identical, the canonical skill is replaced, and no candidate alias remains installed.

Lock fixture hashes, skill hashes, matrix, predicates, and thresholds in the prepared run state before executing any arm. Keep hidden gold outside the prepared run and require its original fixture root explicitly at score time; verify every locked gold hash before scoring. A failed threshold blocks promotion; do not weaken or reinterpret it after seeing results.
