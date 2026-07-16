# Lenses And Findings Contract

## Common Assessment Envelope

Every lens receives the same canonical envelope:

- frozen charter and requirements;
- candidate research package and hashes;
- authoritative evidence roots and exact allowed commands;
- prior raw closure evidence when verifying an existing finding;
- role-specific lens instructions.

The parent must also supply `hash_contract` with value
`sha256-canonical-json-utf8-no-trailing-newline-v1` and the exact verification
command for both payload files:

```bash
python3 skills/research-playbook/scripts/research_package.py hash-json <json-file>
```

`canonical_json_sha256` is the candidate or envelope identity used by the package
controller. `file_sha256` is separately reported for transport diagnostics and is not
the candidate or envelope identity. A lens must compare the declared package hash to
`canonical_json_sha256`; comparing it to `file_sha256` is a contract error.

Exclude producer rationale, expected conclusions, gold fixtures, prior conversational reasoning, other lens outputs, and adjudicator conclusions.

## Exact Lens Terminal Envelope

Every lens returns one JSON object with exactly these two keys and no others:

```json
{
  "verdict": "PASS",
  "findings": []
}
```

`verdict` is exactly `PASS`, `GAPS`, or `BLOCKED`. `findings` is a JSON list. The
parent passes this object unchanged to `research_package.py record-lens` through
`--terminal-envelope`; it does not rename `findings` to `raw_findings`, add lens or
hash metadata, or extract/default fields before validation. `PASS` with an empty
`findings` list is the canonical no-finding result.

Across the three lens outputs, every ID in the candidate's `material_gaps` list must
appear in at least one raw finding so the fresh adjudicator can classify it explicitly.
An accepted planner-owned gap uses the exact ID and proposes `HANDOFF_TO_PLANNER`.
When a candidate gap is unsupported or maturity-invalid, emit an evidence-grounded
`NON_GAP` finding proposing `REJECT_NON_GAP`; never omit the ID silently. The
controller rejects adjudication until all candidate-declared gap IDs are classified.

## Three Lenses

### Internal Readiness

Check self-sufficiency, internal consistency, traceable factual claims, stable terminology, explicit limitations, and whether a fresh planner can understand the package without hidden context. Do not test uncited runtime interoperability here.

For every planner obligation, verify the candidate can support a `READY` record with
grounded implementation anchors, verification anchors, owner, required inputs,
closure condition, and evidence IDs. Missing current-code locations or test
observables is `FIX_IN_RESEARCH` when those surfaces are inside the frozen roots.
Unavailable evidence with no authorized acquisition route or custodian, and an
approval-dependent conflict with no named authority or finite decision contract, is
`BLOCKED_ON_EVIDENCE`; neither may be relabeled as planner-owned readiness.

### Requirements Coverage

Inventory every explicit, implied, negative, and non-functional obligation. Confirm each atomic requirement has a source, maturity, mechanism or research conclusion, acceptance intent, conflict disposition, and explicit inclusion or exclusion. Find omitted and partially decomposed requirements without expanding scope.

### Requirements Satisfaction

Trace each covered requirement at the evidence depth its maturity permits:

- `CURRENT_RUNTIME`: verify producers, consumers, configuration, stored values, degradation paths, and surfaced behavior against real evidence;
- `FUTURE_SYSTEM`: verify consistency with current boundaries, feasibility, acceptance intent, and absence of contradictory requirements without demanding nonexistent runtime evidence;
- split intake `MIXED` records before assessment.

Check intent, not only literal wording. A mechanism that cannot support the requirement's practical outcome is a satisfaction gap.
For every negative coverage or satisfaction answer, verify that its evidence IDs cover
both sides of the conclusion: the evidence that defines the required behavior and the
evidence that demonstrates the missing coverage or behavior. A citation to only one side
is `FIX_IN_RESEARCH`, even when the prose conclusion is correct.

## Exact Raw Finding Record

Every raw finding is one JSON object with exactly these required keys:

- `id`: non-empty string;
- `fingerprint`: non-empty deterministic fingerprint string;
- `lens`: non-empty string equal to the invoked lens role;
- `originating_stage`: exactly `RESEARCH`;
- `requirement_ids`: non-empty list of unique non-empty strings;
- `type`: one exact finding type listed below;
- `materiality`: one exact materiality listed below;
- `practical_consequence`: non-empty string stated before technical evidence;
- `evidence`: either one non-empty string or a non-empty list of non-empty strings;
- `proposed_disposition`: one exact disposition listed below;
- `status`: exactly `OPEN` or `CLOSED`.

The only optional key is `evidence_limitation`, and when present it is a non-empty
string. `closure_evidence` is conditional rather than generally optional: it is
required and non-empty for `CLOSED`, using the same string-or-list shape as
`evidence`, and it is forbidden for `OPEN`.

No aliases, field translation, dropped/default fields, or additional keys are
accepted. In particular, use `findings`, not `raw_findings`, in the terminal envelope;
use `type`, not `finding_type`; and use `originating_stage: RESEARCH`, not the lens
role or phase name.

Finding types are exactly:

- `FACT_GAP`
- `REQUIREMENT_GAP`
- `SATISFACTION_GAP`
- `CONTRADICTION`
- `EVIDENCE_LIMIT`
- `SCOPE_CHANGE`
- `PLANNER_DECISION`
- `NON_GAP`

Materiality is exactly:

- `BLOCKER`: prevents a trustworthy planner handoff;
- `PLANNING`: valid planner-owned work that must be explicit but does not require more research;
- `CLEANUP`: wording or organization only.

## Lens Verdict Mapping

The lens verdict describes whether more **research-stage** work is required. It does
not describe whether the candidate contains a known implementation, policy, or
evidence gap for the planner.

- Return `PASS` when the research question is answered and every emitted finding is
  planner-owned or non-material. A `PASS` lens may therefore emit findings proposed
  as `HANDOFF_TO_PLANNER`, `ACCEPT_LIMITATION`, `MERGE_DUPLICATE`, or
  `REJECT_NON_GAP`.
- Return `GAPS` only when at least one supported finding requires
  `FIX_IN_RESEARCH` inside the frozen charter.
- Return `BLOCKED` only when at least one supported finding requires
  `BLOCKED_ON_EVIDENCE` or `REQUEST_SCOPE_APPROVAL` because the frozen research
  question itself cannot be answered.

A documented absence of runtime proof is not automatically `BLOCKED`. When that
absence conclusively answers the frozen question and the remaining work belongs to
implementation or planning, emit the exact public material-gap candidate `id`,
propose `HANDOFF_TO_PLANNER`, and return `PASS`.

## Adjudication And Dispositions

The fresh adjudicator assigns exactly one disposition:

- `FIX_IN_RESEARCH`: grounded correction inside the frozen research scope;
- `HANDOFF_TO_PLANNER`: legitimate planning-stage work with enough research context;
- `REQUEST_SCOPE_APPROVAL`: material change to the frozen charter;
- `BLOCKED_ON_EVIDENCE`: required accessible evidence is unavailable;
- `ACCEPT_LIMITATION`: explicit bounded uncertainty that does not invalidate planning;
- `MERGE_DUPLICATE`: same practical issue and evidence boundary as another finding;
- `REJECT_NON_GAP`: unsupported, cleanup-only, wrong-stage, or maturity-invalid finding.

Only `FIX_IN_RESEARCH` may cause a parent research edit. `REQUEST_SCOPE_APPROVAL` and `BLOCKED_ON_EVIDENCE` prevent `PASS`. `HANDOFF_TO_PLANNER` must name the affected requirement and the decision the planner must resolve without requesting new research.

Reject a finding as `REJECT_NON_GAP` when it only restates an existing frozen planner
obligation or acceptance intent without identifying an additional unmet decision or
mechanism. In particular, absent deployed proof for a `FUTURE_SYSTEM` requirement is
not a material gap when the frozen requirement already assigns implementation
acceptance criteria to planning. The adjudicator must reject such a finding even when
its ID appears in the public candidate list. The parent validates this maturity rule
before recording adjudication and retries a malformed or maturity-invalid
adjudication under the existing retry budget; it never silently rewrites it.

## Independence And Retry Rules

- Spawn all three lenses concurrently from one immutable envelope.
- Use a unique runtime agent for every role and round.
- Never reuse a lens output as another lens's prompt.
- Permit one retry only for spawn failure, tool failure, malformed terminal envelope, or lost runtime agent.
- A retry receives the same input hash and no diagnosis of the prior output.
- Count the failed attempt and retry against the shared 15-attempt cap.
