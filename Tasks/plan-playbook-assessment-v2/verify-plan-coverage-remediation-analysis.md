# Verify-Plan Coverage Remediation Findings

## Result

The repeated verifier misses expose a convergence-control defect: a coverage item can become `checked` from a sparse findings pass and a coarse critic approval even though the system has no finite record of which verification obligations were assessed. That unsupported status removes the surface from normal later assignment, and `--can-stop` trusts it. A later unrestricted pass can therefore find broad defects in a surface the ledger already treated as complete. The available evidence does not establish why the agents missed those semantic defects; it establishes that the controller could not detect or prevent unsupported completeness.

The stable fix must make verification obligation-level and controller-enforced. Prompt wording alone cannot establish coverage completeness.

## Scope

This assessment covers:

- the live `verify-plan` producer and critic contracts;
- the shared verification-ledger validator and stop gate;
- the `verify-plan` ledger wrapper that delegates to the shared helper;
- the Plan Playbook V2 plan's proposed verifier-output, coverage-approval, and ledger-recording contracts;
- the iteration-32 failure evidence in the Plan Playbook V2 verification ledger.

It does not redesign the other three planning gates, change the Plan Playbook product scope, or suppress valid later findings.

## Confirmed Cause Chain

### Symptom

Iteration 31 marked all `C01-C14` coverage items checked, then iteration 32 found four actionable findings classified `MISSED IN FIRST PASS` across `C04`, `C05`, `C06`, `C08`, `C10`, `C11`, `C13`, and `C14`. The ledger records the repeated failure and resets the queue to `unverified` rather than claiming convergence.

Evidence:

- `Tasks/plan-playbook-assessment-v2/plan-verification-ledger.json:1920-1968`
- `Tasks/plan-playbook-assessment-v2/plan-verification-ledger.json:1475-1508`
- `Tasks/plan-playbook-assessment-v2/plan-verification-ledger.json:1-14`

### Immediate Cause

The verifier emits findings for defects it notices, but it does not emit one closed-world assessment for every assigned verification obligation. The critic classifies those findings and may approve a broad coverage-item status, but the live contract does not define the subclaims that must be exhausted before approval. Silence can therefore be converted into `checked`.

Evidence:

- `skills/verify-plan/SKILL.md:118-141`
- `skills/verify-plan/SKILL.md:143-172`
- `skills/verify-plan/SKILL.md:212-223`

### Deeper Cause

The ledger models broad implementation surfaces rather than finite verification obligations. Its shared validator validates only coarse item fields (`id`, `summary`, `risk`, `status`, and optional evidence paths); callers may add fields, but the helper does not validate or consume them as completeness evidence. It has no schema for assignment, obligation inventory completeness, obligation assessment, evidence-bound conclusion, finding linkage, critic approval, or revision invalidation.

Evidence:

- `skills/_shared/verification_ledger.py:66-123`
- `skills/_shared/verification_ledger.py:126-143`
- `skills/verify-plan/scripts/verification_ledger.py:10-15`

### Downstream Failure

`--can-stop` rejects only high/medium items whose caller-authored status is exactly `unverified`, plus unresolved actionable findings. A falsely checked item therefore passes the deterministic stop gate and drops out of the normal unchecked-item assignment path. The prose rule that stops after broad later misses detects lost confidence only after the defect has already occurred.

Evidence:

- `skills/_shared/verification_ledger.py:126-143`
- `skills/verify-plan/SKILL.md:174-182`
- `skills/verify-plan/SKILL.md:226-232`

## Plan V2 Impact

The current Plan Playbook V2 plan would reproduce the same defect if implemented unchanged:

- role input assigns broad `assigned_coverage_ids`, not stable obligation IDs (`plan.md:240`);
- critic approvals contain only `{coverage_id, prior_status, approved_status, rationale, evidence}` (`plan.md:248`);
- `record-verification-ledger` can prove exact correspondence to those coarse approvals but cannot prove that all required verification obligations were assessed (`plan.md:258-260`).

Therefore the remediation must update both the live helper/skill contract and the corresponding Plan V2 design before the plan can pass verification.

## Stable Fix Boundary

1. The controller creates a finite obligation inventory for each coverage item. Every obligation has a stable ID, source coverage ID, explicit claim, bound plan-section references, evidence references, and dependency references; the inventory has a hash bound to the active plan and evidence revision.
2. An independent critic approves the inventory's completeness against the coverage item's stated risks, contracts, flows, and preservation requirements. The approval names the exact inventory hash and active revisions. An omitted obligation therefore invalidates completeness at the inventory boundary rather than disappearing from verification.
3. Each pass receives explicit assigned obligation IDs from the approved inventory. Progressive slices remain allowed; unassigned obligations remain pending.
4. The verifier emits exactly one assessment for every assigned obligation: `SUPPORTED`, `GAP`, or `BLOCKED`, with evidence and exact finding linkage for `GAP`.
5. The critic emits one fingerprint-bound approval for every obligation assessment, not merely one broad surface-status approval.
6. Completion uses this truth table: only a current, critic-approved `SUPPORTED` assessment can count as complete; `GAP` remains incomplete and actionable; `BLOCKED` remains incomplete and stop-blocking. Neither `GAP` nor `BLOCKED` can contribute to `checked`.
7. The ledger controller derives item completion. It rejects `checked` unless the inventory is independently approved and every currently required obligation is complete on the active plan/evidence revision with no linked actionable finding open.
8. Next-pass assignment and `--can-stop` derive from obligation states, never from a caller-authored broad item status.
9. A plan or evidence change uses the machine-readable plan-section, evidence, and dependency bindings to invalidate affected inventory approvals and obligation assessments while preserving unrelated completed evidence.
10. A later actionable finding against a completed obligation deterministically records coverage failure and prevents convergence; it is never suppressed.

## Required Deterministic Tests

1. A partial high-risk slice leaves the parent item incomplete and assigns the remaining obligation next.
2. A `checked` request with one missing obligation fails validation and cannot stop.
3. An incomplete inventory or an inventory lacking revision-bound completeness approval cannot derive `checked` or pass `--can-stop`.
4. Changing an inventory invalidates its prior approval and requires approval of the new inventory hash before completion can be derived.
5. Complete evidence-bound `SUPPORTED` approvals derive `checked` and can stop when no actionable findings remain.
6. `BLOCKED` cannot derive `checked` and always prevents `--can-stop`.
7. `GAP` without exact linked actionable findings, or `SUPPORTED` with an open linked finding, fails.
8. Missing, duplicate, foreign, omitted, or unassigned obligation assessments and approvals fail.
9. A revision invalidates only affected obligations and preserves unrelated completed evidence.
10. A later finding against a completed obligation enters deterministic coverage-failure state.
11. Legacy ledgers containing only coarse `coverage_checked` IDs cannot establish obligation-level completion.

## Non-Solutions

- Asking the verifier or critic to be more thorough without machine-readable obligation results.
- Requiring exhaustive first-pass inspection.
- Repeating unrestricted full-plan passes until one happens to be clean.
- Resetting every coverage item after every revision.
- Suppressing or downgrading valid later findings.
- Adding hashes around the existing coarse approval shape without changing what is proven.
- Treating the current missed-finding stop rule as prevention; it is only failure detection.

## Research Verdict

`PASS` for identifying the convergence-control root cause. The producer, ledger, stop gate, and Plan V2 consumer can accept unsupported completeness because they do not require an independently approved finite obligation inventory and complete obligation-level results. This verdict does not claim to prove why the agents missed the particular semantic defects. Planning may proceed for the bounded obligation-level contract and tests above; implementation remains approval-gated.
