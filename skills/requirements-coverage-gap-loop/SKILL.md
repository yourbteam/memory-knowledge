---
name: requirements-coverage-gap-loop
description: This skill should be used when a plan, research, or findings document must be audited for requirements COVERAGE — that every requirement the work is supposed to satisfy is actually addressed, and addressed in full. It hunts breadth gaps an internal-readiness or interop review will miss: requirements the document never enumerates (incomplete elicitation), requirements named but with no mechanism (omission), requirements only partially handled across their enumerated sub-cases (partial coverage / decomposition), unreconciled conflicts between requirements, requirements with no testable acceptance criterion, and silently dropped requirements disguised as out-of-scope. Run it before the satisfaction/interop depth pass.
---

# Requirements Coverage Gap Loop

## Goal

Drive a document to **full requirements coverage** through repeated assess-plan-execute cycles. Stop only when the requirement set is demonstrably complete and every requirement — decomposed into its constituent obligations — is either addressed by a specific part of the plan or explicitly and deliberately marked out of scope.

This is the **breadth** check. It is distinct from two siblings:
- `doc-gap-closure-loop` — is the *document* internally self-sufficient and consistent?
- `requirements-satisfaction-gap-loop` — does each *addressed* requirement actually *hold* end-to-end against the real runtime, data, and sibling features (depth)?

Coverage comes first: there is no point depth-testing the satisfaction of a requirement the plan never addressed at all.

## The Question This Loop Answers

> Is the requirement set complete, and is every requirement (and each of its sub-obligations) addressed somewhere in this plan — or explicitly declared out of scope — with a testable acceptance criterion?

A plan can be internally consistent and have every addressed requirement work perfectly, yet silently **omit** a requirement, **half-cover** one, or rest on a requirement set that was never complete. Those are this loop's target. Coverage is about presence and completeness, not correctness of execution.

## Convergence Standard

Convergence requires a fresh full pass over the **complete requirement set** that finds zero blocker coverage gaps: the requirement set is complete (no un-elicited requirement), every requirement decomposes into obligations each traced to an addressing mechanism or an explicit out-of-scope statement, no two requirements conflict without reconciliation, and each requirement carries a testable acceptance criterion.

Hard stop rule: a cycle that found blocker gaps and edited the document may not declare convergence in the same cycle. After any edit, the next required artifact is a fresh `## Cycle N+1 Assessment` over the edited document, with zero open blockers and no further edits.

Loop-until-dry: coverage gaps cluster (find one dropped error-case and adjacent ones often hide too). Keep decomposing and sweeping until one full pass adds nothing.

## Loop

1. Elicit and inventory the complete requirement set.
2. Decompose each requirement into its constituent obligations / sub-cases.
3. Trace each obligation to the plan: addressed, partially addressed, or absent.
4. Record every coverage blocker in a numbered ledger.
5. Plan and apply document edits that close coverage gaps (add the missing mechanism, decompose, reconcile a conflict, add an acceptance criterion, or explicitly scope-out with rationale).
6. Validate, including a post-edit new-gap pass.
7. Return to a fresh full coverage assessment.

## Deterministic Units: Requirements and Their Obligations

The units are **requirements**, each decomposed into **obligations**. Build the set from multiple sources so elicitation itself is complete:

- **Explicit requirements** — stated by the user or the document (quote the source).
- **Implied/derived requirements** — necessarily entailed by the goal even if unstated (e.g. "if it writes data, something must read it"; "if it is user-facing, errors must be handled").
- **Non-functional / cross-cutting requirements** — security, performance, error-handling, observability, backward/forward compatibility, scale, accessibility, data-retention, regulatory — whichever the domain demands.
- **Negative / boundary requirements** — what must NOT happen; behavior at empty/null/max/concurrent/failure conditions.

Then **decompose**: a single requirement usually carries several obligations (each enumerated input, state, error path, role, and boundary). Coverage is assessed per obligation, not per headline requirement — this is how "handles 3 of 5 cases" is caught.

## Assessment Lenses

Apply every lens on every full pass; cite evidence as `path:line` (document section for coverage claims; the requirement source quoted):

1. **Elicitation completeness.** Is the requirement set itself complete? Derive implied, non-functional, and negative requirements the document never enumerates. A missing requirement is the most invisible coverage gap.
2. **Omission (addressed-at-all).** For each requirement, does the plan contain a concrete mechanism/section that addresses it — not merely a mention? "Acknowledged but no mechanism" is uncovered.
3. **Decomposition / partial coverage.** Break each requirement into obligations/sub-cases; is each addressed? Catch enumerated cases, error paths, and boundaries handled for some inputs but not others.
4. **Conflict and consistency.** Do any two requirements conflict (or compete for the same resource/state/ordering)? Does the plan reconcile them explicitly, or will one be silently dropped?
5. **Acceptance-criteria presence / testability.** Does each requirement carry a concrete, testable criterion by which coverage can later be verified? An untestable or vague requirement cannot be confirmed covered.
6. **Scope-boundary explicitness.** Is every deliberately excluded requirement stated as out-of-scope **with rationale**? A silently dropped requirement disguised as "not mentioned" is a coverage gap, not a scope decision.
7. **Traceability (bidirectional).** Can every requirement be traced to a plan section, and every major plan mechanism back to a requirement? Orphan mechanisms (build with no requirement) and orphan requirements (requirement with no mechanism) are both gaps.
8. **Prioritization sanity.** Are must-have requirements covered before nice-to-haves, and is nothing essential deferred without an explicit decision?

## Gap Severity

- `blocker`: a requirement (or an obligation of one) is un-elicited, unaddressed, partially addressed, conflicting-and-unreconciled, untestable, or silently dropped.
- `cleanup`: improves traceability or clarity but coverage holds.

The loop continues for blocker gaps only.

## Gap Ledger

Numbered ledger (`CGAP-001`, …) with: `id`, `severity`, `req_id` (and obligation), `lens`, `evidence (requirement source + where the plan does/does not address it)`, `why it is uncovered`, `planned fix`, `closure evidence`, `status`. Carry every prior id forward each cycle; never renumber.

## Required Assessment Artifact

Produce an auditable artifact each cycle. For anything but a tiny requirement set, create a sibling file named by removing the document's final extension and appending `.coverage-audit.md` (distinct from `.gap-audit.md` and `.satisfaction-audit.md`, so all three can coexist). The response links and summarizes; the file holds the full artifact.

The artifact must include:

- **Requirement Inventory** — every `req_id`, source (quoted), type (`explicit`/`implied`/`non-functional`/`negative`).
- **Obligation Decomposition** — each requirement broken into obligations.
- **Coverage Matrix** — each obligation × {addressed where (`path:line`) / partial / absent / out-of-scope-with-rationale}.
- **Conflict Register** — any requirement pairs in tension and how reconciled.
- **Acceptance-Criteria Table** — each requirement → its testable criterion (or gap).
- **Blocker Gap Ledger** and **Cleanup List**.
- **Gap-To-Fix Map**, **Post-Edit New-Gap Pass**, validation results, and a **Final Coverage Proof** at convergence.

Per-cycle headings exactly: `## Cycle N Assessment`, `## Cycle N Plan`, `## Cycle N Edits`, `## Cycle N Validation`; the final, no-edit cycle adds `## Final Convergence Check`.

Templates:

Requirement Inventory:

| req_id | requirement | type | source (quoted) |
| --- | --- | --- | --- |

Obligation Decomposition:

| req_id | obligation | source/why entailed |
| --- | --- | --- |

Coverage Matrix:

| req_id.obligation | status | addressed where (path:line) / out-of-scope rationale |
| --- | --- | --- |

Blocker Gap Ledger:

| gap_id | severity | req_id.obligation | lens | evidence | why uncovered | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Final Coverage Proof:

| req_id | every obligation covered or scoped-out? | acceptance criterion present? | evidence |
| --- | --- | --- | --- |

## Anti-Shallow-Completion Rules

Never declare convergence when:

- the requirement set was taken as given without an elicitation pass for implied/non-functional/negative requirements;
- requirements were assessed only at the headline level without decomposition into obligations;
- a requirement is "mentioned" in the plan but no addressing mechanism was located;
- a partial-coverage case (some sub-cases handled, others not) was not checked;
- a requirement conflict was noted but its reconciliation was not confirmed;
- a requirement lacks a testable acceptance criterion;
- an excluded requirement is absent rather than explicitly scoped-out with rationale;
- the coverage matrix is missing requirements/obligations, or evidence lacks `path:line`/quoted source.

## Planning & Execution Rules

When gaps exist, write a decision-complete fix plan mapping every open `CGAP` to exact document edits: add the missing mechanism, decompose a requirement and address each obligation, reconcile a conflict, add an acceptance criterion, or add an explicit out-of-scope statement with rationale. Edit the **document** only (not runtime code) unless the user explicitly asks. Do not "cover" a requirement by hand-waving — coverage means a concrete addressing mechanism or an explicit, justified exclusion.

If in Plan Mode, stop after producing the proposed plan; do not edit files.

## Validation Rules

After each edit cycle: re-read each newly-covered requirement and confirm the mechanism (or scope-out) is concrete; re-run the obligation decomposition for any requirement touched; run a post-edit new-gap pass (did adding a mechanism create a new conflict or a new un-decomposed obligation?); confirm every requirement still has an acceptance criterion. Then start the next numbered cycle with a fresh full coverage assessment. Record exact commands/results in the artifact.

## Non-Convergence Rule

Continue while coverage blockers are discoverable and fixable. Report non-convergence only when blocked by a user decision (e.g. whether a newly-elicited requirement is in scope), missing external context needed to know the full requirement set, or an explicit user budget. When a requirement is intentionally excluded, record it as an explicit, rationale-backed out-of-scope item rather than leaving it silently uncovered.

## Handoff

Coverage convergence establishes that every requirement is *addressed*, not that each addressing actually *works*. After this loop converges, run `requirements-satisfaction-gap-loop` to verify each addressed requirement holds end-to-end against the real runtime, data, and sibling features. Full pipeline: `doc-gap-closure-loop` (internal readiness) → `requirements-coverage-gap-loop` (breadth) → `requirements-satisfaction-gap-loop` (depth) → implement.

## Reporting

When the loop converges, report: the document path; the `.coverage-audit.md` path; cycles completed; final gap ledger status; the requirement-set size and decomposition; the key coverage gap classes closed (omission, partial, conflict, missing-criteria, silent-drop); validation results; the compact Final Coverage Proof; and any requirement intentionally excluded (with rationale). State explicitly that convergence means **breadth** (all requirements addressed) and recommend the satisfaction/depth pass next. Do not claim convergence if the artifact is missing, incomplete, or only summarized.
