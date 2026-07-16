# Planner Handoff Contract

## Six-File Package

Emit exactly one directory containing:

1. `manifest.json`: schema version, charter hash, package file hashes, candidate hash, terminal verdict, budget use, and subagent lifecycle evidence.
2. `research.md`: concise findings and grounded conclusions, organized by requirement rather than by research chronology.
3. `requirements.json`: frozen atomic requirements, scope identifiers, sources, maturity, evidence availability, acceptance intent, `research_value_type`, and planner obligations, enriched at emission with terminal research values, evidence IDs, and the structured readiness record for every planner obligation. Frozen requirements use the public intake schema; readiness is added only at emission. Terminal status is never inserted into the pre-research frozen scope.
4. `evidence-index.json`: stable evidence IDs using the exact provenance schema below. It embeds the supported fact and limitation so the planner does not need to open an external source merely to understand the evidence.
5. `findings.json`: deduplicated terminal finding ledger with stage, materiality, disposition, evidence, and closure status.
6. `planner-handoff.md`: an index of the five artifacts above and explicit planning-stage obligations. It adds no hidden rationale or new requirement.

## Candidate Requirement Status Contract

Before any lens runs, the core candidate must include `material_gaps` and
`requirement_statuses`. `material_gaps` is a list of unique non-empty public candidate
IDs; use an empty list when no planner-owned gap is established. Every declared gap
must be explicitly classified during adjudication and cannot disappear through an
empty PASS lens result.

`requirement_statuses` contains exactly one item for every frozen requirement ID.
Each item has exactly these three
keys; do not substitute `status`, `conclusion`, `maturity`, `scope_id`, or limitation
fields inside this array:

```json
{
  "requirement_id": "the exact frozen requirement id",
  "research_value": "the grounded answer using the requirement's frozen research_value_type",
  "evidence_ids": ["stable-evidence-id"]
}
```

Every frozen requirement declares exactly one `research_value_type`: `boolean`,
`number`, `string`, `array`, `object`, or `null`. The value must use that exact JSON
type. For example, a yes/no requirement with `research_value_type: "boolean"` emits
`true` or `false`, never `"Yes"` or `"No"`. Put the explanation in `research.md` and
the supporting fact in the evidence index. The parent rejects a type mismatch during
`record-candidate`, before any lens runs.

`evidence_ids` contains unique non-empty IDs that resolve in the candidate's
`evidence_index`. The IDs must jointly establish the research value and why that value
satisfies or fails the frozen requirement. In particular, a negative coverage or
satisfaction answer must cite both the evidence that defines the required behavior and
the evidence that demonstrates the missing coverage or behavior. Do not attach merely
related evidence that does not support either side of that proof. Put explanations,
maturity labels, limitations, and scope context in `research.md`, the evidence index,
material findings, or planner handoff. The parent must run `record-candidate` before
spawning lenses; material-gap, schema, or frozen-ID coverage errors fail there, not
after hardening.

Canonical JSON files use sorted keys and a trailing newline. The manifest hashes every package file and the frozen charter. Any mismatch invalidates the package.

## Evidence Index Contract

Every evidence item has exactly:

```json
{
  "id": "stable-evidence-id",
  "source_kind": "LOCAL_FILE | SUPPLIED_INPUT | EXTERNAL",
  "source_locator": "path, fixture locator, or URL",
  "source_sha256": "64 lowercase hex characters for local/supplied evidence, otherwise null",
  "accessed_at": "ISO-8601 timestamp for external evidence, otherwise null",
  "supported_claim": "the fact available to the planner",
  "limitations": "what this evidence does not establish"
}
```

Local and supplied evidence requires `source_sha256` and forbids `accessed_at`.
External evidence requires `accessed_at` and a null `source_sha256`.

## Planner Readiness Contract

Before `emit-package`, the parent supplies exactly one readiness item for every unique
planner obligation ID. The controller rejects missing, duplicate, extra, or non-ready
items. Each item has exactly:

```json
{
  "obligation_id": "exact frozen planner obligation id",
  "status": "READY",
  "implementation_anchors": ["grounded file/symbol, operational action, or decision gate"],
  "verification_anchors": ["grounded observable and acceptance boundary"],
  "required_inputs": ["finite input the named owner must supply; empty when none"],
  "owner": "named implementation, evidence, or approval boundary",
  "closure_condition": "observable condition that closes the obligation",
  "evidence_ids": ["stable-evidence-id"]
}
```

Every evidence ID resolves in `evidence-index.json`. `READY` means the planner can
place the obligation into a one-shot plan without discovering an unknown path, owner,
evidence route, policy authority, or acceptance observable. A named approval or
evidence gate may be ready when its owner, required input, route, downstream boundary,
and closure condition are all grounded. A bare instruction to "find", "obtain", or
"ask the proper owner" is not ready.

For current-runtime code work, readiness normally includes concrete source symbols,
test surfaces, fixture boundaries, and observables. For unavailable evidence, it
includes the authorized acquisition route and custodian; otherwise return `BLOCKED`.
For a requirement conflict, it includes the named approval authority and a finite
decision contract that preserves every requirement; otherwise return `BLOCKED`.

## Fresh Planner Envelope

Give the planner only:

- the hashed frozen charter and requirements with maturity;
- the evidence index;
- the final research artifact;
- the terminal findings ledger;
- `planner-handoff.md` as a navigational index.

The input boundary is the recorded six-file directory itself. Bind the planner execution to that directory's canonical tree hash so any file addition, omission, or mutation invalidates the handoff.

Do not give it conversation history, producer explanations, lens outputs, adjudicator reasoning, expected plans, fixture gold, or prior planner attempts.

The planner output has exactly `schema_version`, `claims`, `material_gaps`, and
`planner`. It transcribes the package's claims and terminal material-gap IDs so the
evaluator can prove the handoff did not invent, drift, or drop research conclusions.
It does not recompute those values.

## One-Shot Planner Success

A fresh planner passes only when its plan:

- asks no clarification question;
- maps every frozen requirement to exact implementation and verification steps;
- maps every planning-stage obligation from its structured readiness record without leaving an unowned path, input, evidence route, or decision;
- preserves exclusions, maturity, and approval boundaries;
- cites only evidence present in the package;
- does not demand current-runtime proof for future-system behavior;
- invents no API, schema, file, command, stored value, or runtime fact;
- contains acceptance checks capable of proving the requirement end to end.

If any item fails, the package is not planner-ready even when all research prose appears complete.
