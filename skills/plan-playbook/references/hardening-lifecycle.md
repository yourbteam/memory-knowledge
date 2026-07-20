# Hardening Lifecycle Contract

## Roles and ownership

The parent is the only writer and fixer. Required assessment-only roles are:

- `VERIFY_PLAN_VERIFIER`
- `VERIFY_PLAN_CRITIC`
- `INTERNAL_READINESS`
- `REQUIREMENTS_COVERAGE`
- `REQUIREMENTS_SATISFACTION`

Each attempt uses a fresh runtime agent ID and records the input-envelope hash, output hash, attempt number, completion evidence, close evidence, and released shared-ledger slot. Roles cannot be combined. The critic alone receives the paired verifier's controller-validated raw findings and obligation assessments; no role receives producer rationale, proposed fixes, hidden expected answers, or sibling-lens conclusions.

The controller-validated role input contains exactly `schema_version`, `role`, `round`, `verification_iteration`, `assigned_coverage_ids`, `assigned_obligation_ids`, `lens_contract`, `objective`, `charter`, `requirements`, `plan`, `evidence_index`, `surface_map`, `verification_ledger`, `raw_findings`, `verifier_obligation_assessments`, and `authoritative_roots`. Every file reference is exactly `{path,sha256}`. Each authoritative root is exactly `{repository_key,source_path,source_tree_sha256,snapshot_path,snapshot_tree_sha256,manifest_path,manifest_sha256}`; agents inspect only `snapshot_path`.

Verify-plan roles have a positive globally monotonic iteration, assigned slices, a current ledger, and null lens contract. Owned-lens roles have iteration 1, empty assignments, null ledger, and exact `{id,path,sha256,lens}` identity. Only the critic has non-null paired raw-finding and obligation-assessment snapshots.

## Fixed order

1. Validate the current draft, surface map, decisions, evidence identity, and verification ledger.
2. Build a finite, content-bound obligation inventory. Permit one bootstrap assignment only before the inventory has assignment history; bootstrap supports nothing by itself.
3. Run a verifier and critic on the same assignment and plan hash. The verifier returns exactly one `SUPPORTED|GAP|BLOCKED` assessment per assigned obligation. The critic independently approves or rejects inventory completeness, each assessment, and each finding disposition.
4. Continue deterministic assignments until none remain. A finding touching a supported obligation resets it; changed section, evidence, or dependency bindings selectively invalidate affected assessments.
5. Record `VERIFY_PLAN=PASS` only when `check --can-stop` proves an approved finite inventory, every non-excluded obligation critic-approved `SUPPORTED`, zero GAP/BLOCKED obligations, and zero actionable findings. Coarse section coverage cannot pass this gate.
6. Run fresh `INTERNAL_READINESS` under the immutable owned-lens contract.
7. After its PASS, run a different fresh `REQUIREMENTS_COVERAGE` under the same plan and contract hashes.
8. After its PASS, run a different fresh `REQUIREMENTS_SATISFACTION` under those same hashes.
9. Emit only when all four ordered stages PASS and every attempt slot is released.

## Inputs and artifacts

Every role receives the frozen objective, charter, requirements, current plan, evidence index, surface map, authoritative source snapshots, and role-specific assignments. Verify-plan roles also receive the current ledger. Owned-lens roles receive `{id,path,sha256,lens}` for the run-owned snapshot of `PLAN_PLAYBOOK_V2_HARDENING_LENSES_V1`.

For LIGHT, all four complete Markdown reports are INLINE. For SUBSTANTIAL, verify-plan remains INLINE and the owned lenses materialize exactly:

- `INTERNAL_READINESS` -> `plan.gap-audit.md`
- `REQUIREMENTS_COVERAGE` -> `plan.coverage-audit.md`
- `REQUIREMENTS_SATISFACTION` -> `plan.satisfaction-audit.md`

The controller accepts only the immutable successful attempt output and writes FILE artifacts itself. The parent never reconstructs assessor prose.

Every accepted role output binds `schema_version`, controller-derived attempt ID and input-envelope hash, role, round, verification iteration, assessed plan hash, completion time, findings, dispositions or obligation assessments appropriate to that role, terminal envelope where the role owns one, and one exact artifact transfer. VERIFY_PLAN_VERIFIER cannot claim a terminal verdict; the critic adjudicates its assignment. Each owned-lens role owns its own `PASS|GAPS|BLOCKED` terminal envelope. Unknown or alternate fields fail closed.

## Findings and fixes

Findings identify their stage, source role, requirement/obligation/coverage IDs, practical consequence, exact source or observed evidence, and `ACTIONABLE|NON_ACTIONABLE` classification. Actionable decisions are `FIX NOW` or `IMPLEMENT LATER`; non-actionable decisions are `ACKNOWLEDGE` or `DISMISS`. Only critic-approved verify-plan findings and the named owned-lens assessor's findings may drive a revision.

`GAPS` returns control to the parent. The parent prepares the deterministic revision workspace, changes only its five proposal files, and records the revision with every accepted finding ID. The controller binds OPEN-to-APPLIED transitions, preserves immutable history, resets affected obligations, and invalidates all previous stage PASS records. The next attempt uses the next globally monotonic verify-plan iteration on the new plan hash.

## Bounds and retries

Every prepared attempt consumes budget before spawn. Each role permits one retry. Reserve three attempts for the owned lenses while verify-plan runs. LIGHT permits three revision rounds and at most three successful verifier/critic pairs; SUBSTANTIAL permits three revision rounds and at most ten pairs before an approved continuation. The one continuation permits ten more pairs without resetting attempts, elapsed time, findings, or iteration numbering.

Two consecutive rounds with the same actionable-finding fingerprint, exhausted attempt or elapsed budgets, an unapproved inventory at the limit, or remaining GAP/BLOCKED obligations returns `CAP_REACHED`.

## Terminal mapping

- `PASS`: the current stage established its complete contract with no actionable finding.
- `GAPS`: one or more accepted actionable findings require a plan revision.
- `BLOCKED`: named unavailable evidence, research input, runtime capability, or approval prevents assessment.
- `CAP_REACHED`: the exact configured bound was exhausted.

No BLOCKED or CAP_REACHED state emits a PASS package. Any plan edit invalidates all prior hardening results, even when the edit appears unrelated.
