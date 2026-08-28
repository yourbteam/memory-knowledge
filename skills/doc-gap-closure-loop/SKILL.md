---
name: doc-gap-closure-loop
description: This skill should be used when the user asks to iteratively harden a research, findings, analysis, or planning document until it is ready for a one-shot implementation plan — repeatedly assessing the document for gaps, planning to close them, applying the plan, and looping until no gaps remain.
---

# Doc Gap Closure Loop

## Goal

Drive a document to implementation-planning readiness through repeated assess-plan-execute cycles. Stop only when the assessment finds no gaps that would prevent a follow-up implementation plan from producing a one-shot successful, quality implementation.

## Scope Boundary and Handoff

This loop verifies **internal document readiness**: that the document is self-sufficient, decision-complete, internally consistent, and that the claims and anchors it *cites* are real. That is the limit of what convergence here proves.

This loop does **not** verify, and convergence here must **not** be read as verifying:

- **interop with sibling/already-shipped features** — invariants the document does not cite (e.g. a read path keyed differently than the write path it depends on);
- **runtime/data reality** — whether a field the plan relies on is actually populated and meaningful in the live data (e.g. a "sort by confidence" requirement when the stored confidence is a constant);
- **requirement intent vs mechanism** — whether the mechanism serves the requirement's *intent*, not merely its literal words;
- **end-to-end requirement satisfaction** — tracing each stated requirement through the real cross-service call chain.

These are a different class of gap with a different evidence source (the surrounding codebase, sibling features, stored data, and the requirement set — not the document). The repo-grounding lens here only confirms *cited* claims are true; it does not hunt for *un-cited* invariants, so a document can converge here and still be interop-broken.

**Handoff:** after this loop converges, continue the pipeline before implementing — `requirements-coverage-gap-loop` (breadth: is every requirement addressed?) then `requirements-satisfaction-gap-loop` (depth: does each addressed requirement hold end-to-end against the real runtime, data, and sibling features?). A green convergence here is necessary, not sufficient. Full pipeline: this loop → coverage → satisfaction → implement.

## Convergence Standard

Convergence requires a fresh full-document assessment pass that finds zero blocker gaps. It is not enough to close previously reported gaps.

A stale-word scan, a review of only edited sections, or a statement that prior gaps are fixed is never sufficient evidence of readiness. If each pass continues to expose new blocker gaps, keep looping until one full pass finds none, or report non-convergence with the open blocker classes.

Hard stop rule: a cycle that found blocker gaps and edited the document is not
allowed to declare convergence, even if its validation pass finds no new gaps.
After any document edit, the next required artifact is a new `## Cycle N+1
Assessment` over the already-edited document. Convergence is valid only in a
cycle that starts from the edited document, performs the full assessment, records
zero open blocker gaps, and makes no further document edits.

## Loop

Repeat these steps until the assessment produces no gaps:

1. Inventory every deterministic document unit.
2. Assess the full document from top to bottom using the required assessment artifact.
3. Record every blocker gap in a numbered gap ledger.
4. If blocker gaps exist, create a concrete fix plan.
5. Execute the fix plan.
6. Validate the document, including a post-edit new-gap pass.
7. Return to a fresh full-document assessment.

Treat "no gaps" as the terminal condition. A gap is any missing, contradictory, vague, or insufficiently grounded detail that would force a follow-up implementation planner or implementer to make a decision.

Do not terminate after a partial pass. Do not terminate just because the current cycle fixed all gaps from the prior cycle. The terminal condition is a new full-document pass with no blocker gaps.

If steps 4-6 run in a cycle, step 7 is mandatory and must create the next
numbered cycle's assessment artifact before any convergence claim. The
post-edit new-gap pass and final readiness proof are validation evidence only;
they do not replace the next fresh full-document assessment.

## Deterministic Document Units

Inventory these units before assessment:

- intro text before the first heading
- every heading section
- tables
- schemas or field lists
- locked-decision lists
- examples
- validation, test, and acceptance sections
- appendices
- any unheaded block or list that contains implementation-relevant claims

Every unit gets a stable `unit_id` for the current cycle. Do not use vague coverage labels without identifying the specific text being assessed.

## Gap Severity

Classify each finding:

- `blocker`: prevents a one-shot implementation plan or forces a planner or implementer to decide something the document should decide.
- `cleanup`: improves wording, organization, or readability but does not block implementation planning.

The loop continues for blocker gaps only. Cleanup findings may be reported or fixed when nearby, but do not create endless churn for cleanup-only issues.

## Gap Ledger

Maintain a numbered ledger during the loop:

- Assign each blocker a stable ID such as `GAP-001`.
- Record these columns for each blocker: `id`, `severity`, `section`, `lens`, `evidence`, `why it blocks`, `planned fix`, `closure evidence`, and `status`.
- In the fix plan, map every open gap ID to the exact section changes that will close it.
- After editing, mark each prior gap closed only when the document now contains the missing decision or grounded detail.
- If an edit exposes or creates another blocker, add it as a new gap ID instead of treating the cycle as converged.
- Carry forward every prior gap ID in each cycle as `open`, `closed`, or `superseded`.
- Do not renumber prior gaps. New gaps always receive new IDs.
- Closed and superseded gaps must retain closure or supersession evidence.

## Required Assessment Artifact

Each assessment cycle must produce an auditable assessment artifact. Internal notes may be used, but they do not satisfy the skill.

For small documents, the full assessment artifact may be visible in the response. A response-only artifact is allowed only when the document is `<= 200` lines and has `<= 12` deterministic document units.

For all larger documents, create or update a sibling audit file. Derive its name by removing the final extension from the target document filename and appending `.gap-audit.md`; for example, `workflow1-image-link-prephase-research-findings.md` becomes `workflow1-image-link-prephase-research-findings.gap-audit.md`.

Use a sibling audit file when the document has more than `200` lines, more than `12` deterministic document units, or when the full artifact would be too large to show without summarizing. The response must link to the audit file and summarize it, but the audit file must contain the full artifact. A summarized response alone cannot satisfy convergence.

The artifact must include:

- a section inventory covering every deterministic document unit
- a section-by-section coverage matrix
- the blocker gap ledger
- a cleanup list, if cleanup findings exist
- closure proof for previously open blocker gaps
- a gap-to-fix map for the current cycle
- a post-edit new-gap pass
- exact validation commands and concise command results
- final readiness proof when claiming convergence

Every audit-file cycle must use these headings exactly:

- `## Cycle N Assessment`
- `## Cycle N Plan`
- `## Cycle N Edits`
- `## Cycle N Validation`

The final cycle must also include `## Final Convergence Check`. Prior gap IDs must be carried forward under the cycle assessment or validation section.

The final cycle must be a no-edit assessment cycle. If `## Cycle N Edits`
contains any document edit, `## Final Convergence Check` is forbidden in Cycle N.
The earliest valid convergence artifact is `## Cycle N+1 Assessment` followed by
`## Final Convergence Check`, with no `## Cycle N+1 Plan` or `## Cycle N+1 Edits`
unless that fresh assessment finds blockers.

Do not move from assessment to planning until the current assessment artifact covers the whole document. One assessment pass must keep collecting visible blocker gaps until every section has been inspected.

Use these templates:

Section Inventory:

| unit_id | section/title | unit type | implementation relevance |
| --- | --- | --- | --- |

Coverage Matrix:

| unit_id | lens | status | evidence |
| --- | --- | --- | --- |

Blocker Gap Ledger:

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Gap-To-Fix Map:

| gap_id | target unit | exact decision to lock | edit summary | validation check |
| --- | --- | --- | --- | --- |

Cleanup List:

| item_id | unit_id | issue | optional fix |
| --- | --- | --- | --- |

Post-Edit New-Gap Pass:

| changed unit | checked against | result | new gap id |
| --- | --- | --- | --- |

Final Readiness Proof:

| category | status | evidence |
| --- | --- | --- |

## Section Coverage Matrix

For each document unit, check every assessment lens and mark it as:

- `checked`: inspected with a short evidence note
- `gap found`: inspected and recorded in the blocker ledger or cleanup list
- `not applicable`: explicitly not relevant to that section, with a short reason when non-obvious

`not applicable` is allowed only with a concrete reason in the evidence column. A section cannot be skipped silently. A convergence claim is invalid unless the matrix shows every unit was assessed against every lens.

## Assessment Rules

Assess against the exact implementation-planning question:

> Does this document contain enough grounded detail for a follow-up implementation plan to result in a one-shot successful and quality implementation?

Apply every assessment lens on every full pass:

- implementation decision completeness
- runtime entry points and data flow
- schema, field, helper, artifact, and API semantics
- edge cases, failure behavior, resume behavior, and idempotency
- validation commands, test scenarios, and acceptance criteria
- repo grounding for each runtime claim
- approval boundaries and out-of-scope slices
- contradictions between sections
- vague or flexible wording that hides implementation choices
- implementation planner handoff readiness

Use local repo inspection for discoverable facts before reporting a gap. Do not ask the user for facts that can be verified from code, config, tests, or the document itself.

When the document makes repo/runtime claims, either confirm them from code and preserve a concrete reference in the document, or mark the missing grounding as a blocker gap.

When a finding or closure depends on document text, cite the exact section or heading. When it depends on repo/runtime behavior, cite the concrete file, config, test, or command output used as evidence.

Evidence must be concrete. For local markdown files and repo files, use `path:line` evidence for document claims and repo/runtime claims. Gather local line-number evidence with `nl -ba`, `rg -n`, or an equivalent line-numbered command before citing it. Section-only evidence is allowed only when the source is not a local file or line numbers are genuinely unavailable. Unsupported phrases such as "looks complete", "seems covered", or "appears ready" do not count as evidence.

## Anti-Shallow-Completion Rules

Never declare convergence when:

- the same cycle found blocker gaps and then edited the document
- only recently edited sections were reviewed
- only stale wording was searched
- only one or two obvious gaps were considered and the full assessment lenses were not applied
- any section still contains unresolved implementation choices
- any locked decision conflicts with another section
- repo/runtime claims remain ungrounded
- the validation pass only proves prior gaps were fixed
- the section coverage matrix is missing sections or relevant lenses
- the gap ledger lacks evidence or closure evidence for blocker rows
- the assessment artifact is missing, incomplete, or only summarized
- a required large-document audit file is missing
- `not applicable` statuses lack concrete reasons
- local document or repo evidence lacks `path:line` references

## Planning Rules

When gaps exist, create a plan that is decision-complete for editing the document. The plan must identify:

- exact document sections to add or revise
- exact decisions to lock
- wording classes to remove or tighten
- validation commands to run after editing

In normal execution, accept the plan and apply it immediately. The gap-to-fix map must still be visible in the response or recorded in the audit file; hidden planning alone does not satisfy the skill.

The plan must cover every open blocker in the gap ledger. Do not plan fixes for only the easiest findings while leaving other blocker gaps for later.

Do not start the fix plan until the current assessment pass has completed the section inventory, coverage matrix, and blocker ledger for the whole document. Finding several blockers early does not allow the assessment pass to stop.

## Execution Rules

Apply only document changes unless the user explicitly asks to change runtime code. Preserve the document's existing structure and terminology where it is correct.

For each edit cycle:

- update the document to close every reported gap
- remove or tighten wording that implies unresolved decisions
- keep approval-sensitive contract or persona text explicitly approval-gated
- avoid introducing new implementation commitments that are not grounded in the document or repo
- update closure evidence for every blocker gap the edit claims to close

If the environment is in Plan Mode, stop after producing the proposed plan. Do not edit files in Plan Mode.

## Validation Rules

After each edit cycle, run a focused validation pass:

- scan the document for unresolved terms relevant to the task, for example `TBD`, `TODO`, `maybe`, `could`, `should`, `candidate`, `not locked`, `needs further`, `or equivalent`, and `such as`
- run `git diff --check` for edited tracked files when available
- re-read the edited sections and confirm each prior gap is closed
- re-read all locked decisions, exact deltas, validation criteria, and out-of-scope sections
- confirm repo-grounded claims still have concrete references or are explicitly qualified
- run a post-edit new-gap pass for contradictions, ungrounded claims, approval-sensitive commitments, missing validation, or scope drift introduced by the edits
- run a delta regression pass comparing changed text against all locked decisions, prior closure evidence, approval boundaries, repo-grounded claims, and out-of-scope statements
- after any edit cycle, start the next numbered cycle with a fresh full-document
  assessment; do not substitute a validation/readiness pass for that assessment
- record the exact validation commands and concise command results in the audit artifact or, for a response-only small-document run, in the response artifact

If validation reveals remaining gaps, continue the loop.

## Final Readiness Proof

Before reporting convergence, produce a final readiness proof that marks each implementation-planning category as `ready` with evidence:

- runtime entry points and data flow
- schema, fields, interfaces, helpers, and artifacts
- edge cases and failure behavior
- resume behavior and idempotency
- validation commands, test scenarios, and acceptance criteria
- repo grounding
- approval boundaries
- out-of-scope boundaries

If any category cannot be marked `ready`, record a blocker gap and continue the loop.

## Non-Convergence Rule

Continue looping while blockers are discoverable and fixable from the document or repo. Do not stop merely because new fixable blockers keep appearing.

Report non-convergence only when blocked by a user decision, approval-sensitive wording, missing external context, inaccessible required evidence, or an explicit user-imposed cycle or time budget.

## Reporting

When the loop converges, report:

- the document path
- the audit file path when one was required or created
- the number of assessment/fix cycles completed
- the final gap ledger status
- the final section coverage summary
- the key gap classes closed
- the validation commands and results
- why the final full-document pass found no blocker gaps
- the compact final readiness proof with evidence

Scope the convergence claim honestly. State that convergence means **internal document readiness only** — the document is self-sufficient and internally consistent — and that it does **not** establish interop, runtime/data-reality, or end-to-end requirement correctness. Do not report the document as "ready for one-shot quality implementation" without that caveat. End the report by recommending a `requirements-interop-gap-loop` pass as the next step before implementation.

Do not claim convergence if the audit artifact is missing, incomplete, or only summarized.

For response-only small-document runs, the final response must include the full final section inventory, final gap ledger summary, validation command results, and readiness proof.

If convergence is blocked, report the exact blocker and the decision needed from the user.
