---
name: requirements-satisfaction-gap-loop
description: This skill should be used when a plan, research, or findings document needs to be verified for requirements SATISFACTION — that each requirement the plan addresses will actually hold end-to-end once built, against the real runtime, the live/stored data, and the sibling/already-shipped features it must interoperate with. It is a depth check: it catches gaps an internal-readiness or coverage review structurally cannot — cross-feature contract mismatches (a read path keyed differently than the write path it depends on), requirements that fail against real stored-data values (a "sort by confidence" when stored confidence is constant), mechanisms that satisfy a requirement's literal words but not its intent, configuration dependence, and best-effort paths that silently degrade to inert or wrong results. Run it AFTER a coverage pass confirms every requirement is addressed.
---

# Requirements Satisfaction Gap Loop

## Goal

Drive a plan to **end-to-end satisfaction readiness** through repeated assess-plan-execute cycles. Stop only when every requirement the plan addresses is traced to concrete evidence that, once built, it will actually be satisfied against the real runtime, the live/stored data, and the sibling features it must interoperate with — and no producer/consumer or read/write invariant is broken.

This is the **depth** check. It presupposes its siblings have run:
- `doc-gap-closure-loop` — the *document* is internally self-sufficient and consistent.
- `requirements-coverage-gap-loop` — every requirement is *addressed* (breadth).

This loop then asks: of the requirements the plan addresses, do they actually **hold**? There is no point depth-testing a requirement coverage already proved is addressed, unless coverage confirmed it is addressed — so run coverage first.

## The Question This Loop Answers

> If a competent implementer builds exactly what this document says, will the running system actually satisfy each addressed requirement — given the code it does not cite, the data it does not inspect, and the sibling features it must interoperate with?

A document can be internally consistent, cover every requirement, and have every cited anchor real, yet an addressed requirement still fails in practice because the mechanism collides with code, data, or a sibling feature outside the document. Those failures are this loop's entire target. Satisfaction is about correctness of execution, not presence of a mechanism.

## Why a Separate Loop (Evidence Source)

Internal-readiness review verifies the claims a document **makes** and the anchors it **cites**; coverage review verifies each requirement is **addressed**. The gaps this loop hunts live **outside** the document and outside the question of presence:

- the **un-cited** sibling/already-shipped feature the plan must match (the write path a new read path depends on);
- the **actual values** in stored/live data, not just the schema;
- the **real cross-service call chain**, not the doc's local anchors;
- the requirement's **intent**, not its literal wording.

So this loop must read into code, schemas, migrations, fixtures, and live-data semantics the document never mentions. Evidence drawn only from the document is never sufficient here.

## Convergence Standard

Convergence requires a fresh full pass over the **addressed requirement set** that finds zero blocker gaps — every addressed requirement traced end-to-end to confirming evidence, and every producer/consumer and read/write pair checked for symmetric handling. Closing previously reported gaps is not enough.

Hard stop rule: a cycle that found blocker gaps and edited the document may not declare convergence in the same cycle. After any edit, the next required artifact is a fresh `## Cycle N+1 Assessment` over the edited document, with zero open blockers and no further edits.

Loop-until-dry: these gaps come in classes (find one key-namespace mismatch and others may hide in adjacent fields). Keep sweeping the requirement set and every producer/consumer boundary until one full pass comes up empty.

## Loop

1. Inventory the addressed requirements (the deterministic units; reuse the coverage pass's set if available).
2. Build an end-to-end runtime trace for each, reading into un-cited code/data.
3. Assess every requirement and every interop boundary against the required lenses.
4. Record every blocker gap in a numbered ledger.
5. Plan and apply document edits that lock the corrected contract.
6. Validate, including a post-edit new-gap pass.
7. Return to a fresh full satisfaction assessment.

## Deterministic Units: the Addressed Requirement Set

The units are the **requirements the plan addresses** (depth), each with a stable `req_id`. Where a `requirements-coverage-gap-loop` ran first, take its converged requirement set as the input. Also re-confirm **implied-essential** satisfaction requirements that only become visible at depth (e.g. "the read key must equal the write key", "the ranking field must be meaningful in the data"), and the **interop invariants** the plan must hold with sibling features.

## Assessment Lenses

Apply every lens to every requirement on every full pass. Evidence must come from the real system, cited as `path:line` (or schema/migration/fixture/query output):

1. **Cross-feature contract invariants.** For any value crossing a feature boundary (key, id, schema, ordering, units, encoding, enum, timestamp), does the consumer produce/interpret it identically to the producer? Read **both** sides. Canonical failure: a new read path keys or resolves a value differently than the shipped write path it reads from.
2. **Data-reality vs requirement.** Is every field a requirement depends on actually populated and meaningful in the live/stored data? Inspect insert sites, defaults, migrations, and real values — not just the schema. A requirement to rank/filter/branch on a field is broken if that field is constant, null, or defaulted in practice.
3. **Intent vs mechanism.** Does the mechanism serve the requirement's *intent*, or only its literal words? State the intent, then check the mechanism against it.
4. **End-to-end runtime trace.** Follow each requirement through the actual call chain across every service/process, from trigger to stored effect to surfaced result. Confirm each hop exists and passes the needed data.
5. **Producer/consumer symmetry.** Wherever a producer normalizes, resolves, hashes, or defaults an input, confirm the consumer does the same (or is fed the producer's resolved output). Asymmetric resolution silently generates mismatches.
6. **Silent-inert / silent-wrong detection.** Trace every best-effort / graceful-degradation path: where could a misconfiguration, empty result, or swallowed error masquerade as a benign "nothing here" while the real condition is failure?
7. **Configuration & environment dependence.** Does the requirement silently depend on an operator/env/config value being set and matching another component's value? If unset/mismatched, does the feature fail loudly or go quietly inert?
8. **Scope-vs-usage reality.** Does the chosen surface (the place the plan hooks) match how the feature is actually exercised? A correct mechanism on a path the user never takes does not satisfy the requirement.

## Gap Severity

- `blocker`: implementing the plan as written would leave an addressed requirement unsatisfied end-to-end, break an interop invariant, or let a real failure pass silently.
- `cleanup`: improves robustness/observability/clarity but the requirement still holds.

The loop continues for blocker gaps only.

## Gap Ledger

Numbered ledger (`SGAP-001`, …) with: `id`, `severity`, `req_id`, `lens`, `evidence (both sides, path:line / data)`, `why it breaks the requirement`, `planned fix`, `closure evidence`, `status`. Carry every prior id forward; never renumber.

## Required Assessment Artifact

Produce an auditable artifact each cycle. For anything but a tiny requirement set, create a sibling file named by removing the document's final extension and appending `.satisfaction-audit.md` (distinct from `.gap-audit.md` and `.coverage-audit.md`). The response links and summarizes; the file holds the full artifact.

The artifact must include:

- **Requirement Inventory** — every `req_id`, source (quoted), type (`stated`/`implied-essential`/`invariant`).
- **End-to-End Trace Table** — per requirement, the real call chain with `path:line` evidence and the stored-data/config facts it depends on.
- **Lens Coverage Matrix** — every requirement × every lens, `checked`/`gap found`/`not applicable` (with reason).
- **Blocker Gap Ledger** and **Cleanup / Known-Limitation List**.
- **Gap-To-Fix Map**, **Post-Edit New-Gap Pass**, validation results, and a **Final Readiness Proof** at convergence.

Per-cycle headings exactly: `## Cycle N Assessment`, `## Cycle N Plan`, `## Cycle N Edits`, `## Cycle N Validation`; the final, no-edit cycle adds `## Final Convergence Check`.

Templates:

Requirement Inventory:

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |

End-to-End Trace Table:

| req_id | trace (trigger → … → surfaced result) | runtime/data evidence (path:line / value) | holds? |
| --- | --- | --- | --- |

Lens Coverage Matrix:

| req_id | lens | status | evidence |
| --- | --- | --- | --- |

Blocker Gap Ledger:

| gap_id | severity | req_id | lens | evidence (both sides) | why it breaks the requirement | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Final Readiness Proof:

| req_id | satisfied end-to-end? | evidence |
| --- | --- | --- |

## Anti-Shallow-Completion Rules

Never declare convergence when:

- evidence was drawn only from the document and not from the surrounding system;
- a producer/consumer or read/write boundary was checked on only one side;
- a data-dependent requirement was checked against the schema but not against actual stored values/defaults/insert sites;
- a best-effort path was not traced for silent-inert/silent-wrong behavior;
- the same cycle found blockers and then edited and declared convergence;
- the lens coverage matrix is missing requirements or lenses, or `not applicable` lacks a concrete reason;
- any `path:line`/data evidence is missing for a ledger or trace row.

## Planning & Execution Rules

When gaps exist, write a decision-complete fix plan mapping every open `SGAP` to exact document edits, then apply it. Edit the **document** only (lock the corrected contract — e.g. "consumer resolves the key via the same resolver the producer uses"; "order by the meaningful signal, not the constant field"). Do not change runtime code unless the user explicitly asks; when the correct fix is a runtime change, record it as a required implementation step in the document and as closure evidence, not as a code edit.

If in Plan Mode, stop after producing the proposed plan; do not edit files.

## Validation Rules

After each edit cycle: re-read every changed requirement contract; re-run the relevant end-to-end traces to confirm the fix closes the gap against real code/data; run a post-edit new-gap pass (did the fix introduce a new interop asymmetry or scope drift?); confirm every runtime/data claim still carries concrete evidence. Then start the next numbered cycle with a fresh full satisfaction assessment. Record exact commands/results in the artifact.

## Non-Convergence Rule

Continue while blockers are discoverable and fixable from the document, repo, or data. Report non-convergence only when blocked by a user decision (e.g. an accepted scope limitation that leaves a requirement unmet by design), an approval-sensitive change, inaccessible required evidence (e.g. a live store that cannot be inspected), or an explicit user budget. When an accepted scope decision leaves a requirement unsatisfied, record it explicitly as a known limitation rather than masking it as satisfied.

## Handoff

This is the last gate before implementation. Full pipeline: `doc-gap-closure-loop` (internal readiness) → `requirements-coverage-gap-loop` (breadth: all requirements addressed) → `requirements-satisfaction-gap-loop` (depth: each holds end-to-end) → implement.

## Reporting

When the loop converges, report: the document path; the `.satisfaction-audit.md` path; cycles completed; final gap ledger status; the key satisfaction/interop gap classes closed; validation results; why the final full pass found no blocker gaps; and the compact Final Readiness Proof (every addressed requirement → satisfied end-to-end, with evidence). State explicitly any requirement that remains unmet by an accepted scope decision. Do not claim convergence if the artifact is missing, incomplete, or only summarized.
