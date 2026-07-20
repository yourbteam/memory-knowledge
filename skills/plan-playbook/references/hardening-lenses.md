# Plan V2 Hardening Lenses

Contract ID: `PLAN_PLAYBOOK_V2_HARDENING_LENSES_V1`

This file is the complete immutable owned-lens contract. The controller hashes its raw bytes at initialization and binds that hash to every owned-lens input, result, package, replay, evaluation, and promotion check. Standalone V1 hardening skills are design provenance only; do not import, invoke, or consult them at runtime.

## Shared assessor contract

Each lens runs once per hardening round in its own fresh assessment-only subagent. All three receive the same frozen objective, charter, requirements, plan bytes and hash, evidence index, surface map, authoritative source snapshots, and this run-owned contract snapshot and hash. They receive no sibling result, producer rationale, proposed fix, or hidden expected answer.

Every report begins with these exact Markdown sections in this order:

1. `## Lens Contract` - exact contract ID and raw-byte SHA-256.
2. `## Assessed Plan` - exact assessed plan SHA-256 and revision.
3. `## Verdict` - exactly `PASS`, `GAPS`, or `BLOCKED`.
4. `## Findings` - entries that reconcile one-to-one with machine findings, or the explicit statement `No findings.`

Each finding states its ID, affected requirement/obligation IDs, practical consequence, exact evidence, source classification, and disposition recommendation. Findings remain within the active lens. `FIX NOW|IMPLEMENT LATER` is actionable and requires `GAPS`; `ACKNOWLEDGE|DISMISS` is non-actionable. A finding cannot be borrowed from another lens to manufacture or prevent PASS.

Shared verdict rules:

- `PASS`: every required lens section contains evidence and no actionable finding remains in this lens.
- `GAPS`: one or more evidence-backed actionable findings exist in this lens.
- `BLOCKED`: a named unavailable evidence or runtime boundary prevents completing this lens; identify what is missing and why the conclusion cannot be reached.

An empty required section, foreign plan or contract hash, missing evidence, unknown section, mixed-lens conclusion, or structurally valid prose that does not establish this lens is invalid output, not PASS.

## INTERNAL_READINESS

### Purpose

Determine whether this plan itself is a grounded, internally coherent, decision-complete instruction set that a competent implementer can execute without rediscovery or unstated choices. This lens does not count whether every requirement category is present and does not predict whether the proposed implementation will satisfy real runtime behavior; those belong to the next two lenses.

### Required questions

- Does each factual or architectural claim used by the plan trace to frozen evidence?
- Do plan sections, surface maps, decisions, ordering, dependencies, and verification instructions agree with one another?
- Are all in-scope design and operator choices locked, with no either/or, optional, placeholder, or deferred decision language?
- Can an implementer identify exact files, entry points, contracts, implementation actions, prerequisites, and expected verification observables without new investigation?
- Does the plan's preflight prove every claimed existing file, fixture, symbol, and test command
  from frozen source, and label absent files as `CREATE` instead of describing them as existing?
- Does the controller-validated behavior matrix contain grounded or explicitly excluded input
  categories, every affected downstream consumer and aggregate, and one concrete observable,
  command, and assertion for every state-by-consumer pair? Are malformed-success envelopes and
  multi-entity reuse states represented whenever the producer contract allows them?
- When frozen repository configuration exposes a native full regression-suite command, does the
  plan run focused behavioral verification first and that native full suite second; or does it
  provide evidence that no such repository command exists?
- Are failure handling, rollback/recovery, ownership, and approval boundaries executable where the change requires them?

### Required report sections

After the shared sections, include exactly:

1. `## Grounding`
2. `## Internal Consistency`
3. `## Decision Completeness`
4. `## Implementation Readiness`

Each section cites concrete plan anchors and frozen source evidence. PASS requires all four to be affirmatively established. Missing requirement breadth alone is not an INTERNAL_READINESS finding unless it creates a contradiction or makes the plan non-executable.

## REQUIREMENTS_COVERAGE

### Purpose

Determine whether the plan accounts for the complete frozen requirement universe. This is a breadth and traceability lens: it does not decide whether the chosen implementation will work at runtime and does not repeat general plan clarity checks.

### Required questions

- Is every explicit requirement represented by plan obligations and concrete implementation and verification anchors?
- Where behavior partitions by success, error, malformed input, precedence, or state, does the
  plan enumerate every materially distinct branch and mixed state rather than only happy paths?
- Are implied requirements necessary to make the requested behavior complete represented and traceable to evidence?
- Are negative requirements, prohibited behavior, exclusions, and scope boundaries preserved rather than silently omitted?
- Are relevant nonfunctional requirements such as safety, determinism, recovery, compatibility, performance, security, and operability included when grounded by the charter or evidence?
- Is every exclusion explicit, approved by the frozen charter, and prevented from leaking back into planned work?
- Does every requirement and obligation map to at least one PLANNED surface, or to a valid charter-backed exclusion?

### Required report sections

After the shared sections, include exactly:

1. `## Requirement Inventory`
2. `## Explicit Requirements`
3. `## Implied Requirements`
4. `## Negative Requirements`
5. `## Nonfunctional Requirements`
6. `## Exclusions`

The inventory reconciles every frozen requirement and planner obligation exactly once. Each category records covered IDs, plan anchors, verification anchors, and evidence, including an explicit evidence-backed `None` when a category truly has no members. PASS requires no omitted, partially represented, broadened, or incorrectly excluded requirement. A fully represented but technically unsound action is not a COVERAGE finding; it belongs to REQUIREMENTS_SATISFACTION.

## REQUIREMENTS_SATISFACTION

### Purpose

Determine whether following the plan would make every addressed requirement actually hold end to end against the real code, runtime, data, integration boundaries, and already-shipped sibling behavior. This is a causal adequacy lens: it assumes the frozen inventory and asks whether the planned mechanism and proof are sufficient.

### Required questions

- For each addressed requirement, does the planned cause-and-effect chain reach the required user or system observable?
- Do the named code paths, schemas, APIs, state transitions, persistence behavior, and runtime ownership match the authoritative sources?
- Are data identity, normalization, ordering, nullability, mutation, migration, and failure semantics preserved where applicable?
- Do producer and consumer boundaries agree end to end, including restart, replay, recovery, and error paths?
- Does each behavioral branch trace through every downstream renderer, counter, persistence path,
  or other consumer, with precedence preserved when states overlap?
- Does the plan preserve compatible behavior of already-shipped sibling features and avoid bypassing their authoritative contracts?
- Would the listed verification steps actually observe requirement satisfaction through the same path real consumers use, including negative and failure cases?
- Do parser and validator tests prove semantic data validity, not merely section presence or schema
  shape, and do mixed error-plus-output cases fail according to the locked precedence?

### Required report sections

After the shared sections, include exactly:

1. `## End-to-End Claims`
2. `## Code and Runtime`
3. `## Data Semantics`
4. `## Integration Boundaries`
5. `## Sibling Behavior`

Each addressed requirement is traced from planned change through its real producer, boundary, consumer, and observable verification. A section may state evidence-backed non-applicability, but may not be empty. PASS requires that every addressed requirement's complete causal chain and proof hold. An absent requirement belongs to REQUIREMENTS_COVERAGE; unclear prose belongs to INTERNAL_READINESS unless it prevents proving the causal chain.

## Separation test

Before returning a finding, apply this discriminator:

- "Can an implementer execute the plan without rediscovery or a choice?" -> `INTERNAL_READINESS`.
- "Did the plan include every kind and instance of required work or valid exclusion?" -> `REQUIREMENTS_COVERAGE`.
- "Would the included work and verification actually make the requirement true end to end?" -> `REQUIREMENTS_SATISFACTION`.

If evidence supports more than one independent defect, emit a distinct finding under each applicable lens. Do not duplicate one defect verbatim across lenses.
