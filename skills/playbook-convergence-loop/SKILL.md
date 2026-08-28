---
name: playbook-convergence-loop
description: Use only when Kamen explicitly asks for the full research, planning, implementation, and review chain to run autonomously to convergence. Creates a bounded autonomy envelope, independently hardens research and plans, implements without commits by default, reviews every in-scope working-tree surface, and loops from validated review gaps back to research until no requirement gap remains. Do not use for research-only, plan-only, review-only, or assessment requests.
---

# Playbook Convergence Loop

Run research -> research gates -> Planner -> implementation -> review. Return validated review gaps to research and repeat. Tests are evidence, not the definition of convergence.

## Authorization Envelope

Explicit invocation authorizes edits only inside the objective, requirement set, hardened plan, named repositories, and recorded allowed paths. It does not authorize directive promotion without `lock it`, secrets, credentials, deployment, destructive actions, external messages, scope expansion, or commits unless separately approved. A new requirement or plan expansion creates an approval blocker and returns to research after approval.

Default `commit_policy` is `none`. Never commit because a nested skill historically requested it.

## State And Baseline

Before source edits:

1. Create or migrate one schema-v1 task state with `convergence_state.py` at `${XDG_STATE_HOME:-$HOME/.local/state}/kamen-convergence/<task-id>/state.json`.
2. Record every Git repository and non-Git managed path that may change. Protect initial dirty paths with metadata/hashes only; never copy unrelated or secret contents.
3. Record immutable base state and mutable expected state. Track generated-region evidence for an approved dirty projection overlap.
4. Run `guard-baseline` before every edit, reviewer spawn, finding fix, verification command, install, or projection mutation. Stop on unexplained branch, HEAD, index, path, or tree drift.
5. Review the union of committed, staged, unstaged, and new in-scope files for every recorded surface.

The canonical convergence state path above is also the only outer state passed to Planner. Do not create a second convergence state or planning authorization store.

## Delegation

The parent orchestrator is the only fixer and task-state writer. Verification agents inspect and report in assessment-only mode.

Fresh reasoning context excludes producer rationale, hidden expected answers, prior conversational reasoning, and producer explanations. It includes the objective, full assigned requirements, artifact, authoritative source roots, exact diff/runtime commands, raw findings, and raw closure evidence.

Parent-runtime spawn/wait/close capability determines subagent availability. A delegated agent is not expected to spawn children. If parent subagent tools are unavailable, stop rather than self-review.

Use `skills/_shared/STAGE_RESULT_CONTRACT.md` for every delegated result. The parent validates and records its envelope.

## Slot Lifecycle

Use `skills/_shared/agent_slot_ledger.py` serially, normally with `--max 1`:

1. Before acquisition, record every runtime-ID-bearing slot command in the selected sequence or discovery document using fixed-position placeholders, for example `bind-agent --slot-id <slot-id> --agent-id <agent-id>`. Guard later concrete commands against these shapes; the executable, subcommand, ledger, flags, label, and token count remain exact while only the placeholder token may vary.
2. `guard`, then `acquire --label <stage>` and capture the returned slot id. Labels are reusable stage descriptions; they are not unique selectors once released tombstones exist.
3. Spawn; immediately guard and run `bind-agent --slot-id <returned-slot-id> --agent-id <returned-id>` against the pre-recorded shape.
4. Wait and collect full output; guard and run `mark-completed --slot-id <returned-slot-id>` against its pre-recorded shape.
5. Reach the host-accurate terminal boundary for that exact returned id: on a host with a runtime `close_agent` operation (Codex), call it; on a host without one (Claude), verify process-terminal completion evidence through `skills/_shared/host_agent_runtime.py` instead of inventing a close call.
6. Guard and run `mark-closed --slot-id <returned-slot-id> --close-evidence <previous-status>`, then `release --slot-id <returned-slot-id>`, each against its pre-recorded shape.

If spawn fails before an id, abandon the reservation by slot id. If bind fails after spawn, drive the runtime agent to its host-accurate terminal boundary, abandon by slot id with runtime id and close evidence, then release by slot id. Never use a reusable label for mutation after acquisition. Never use `reap` for a live or unknown agent. At iteration boundaries require zero active slots; compact released tombstones only after status proves zero.

## Stage Order

Read each named skill when its stage begins:

1. Direct evidence collection against the declared real repository, runtime, and primary-source boundary
2. `doc-gap-closure-loop` in delegated assessment-only mode until PASS
3. `requirements-coverage-gap-loop` in delegated assessment-only mode until PASS
4. `requirements-satisfaction-gap-loop` in delegated assessment-only mode until PASS
5. `plan-playbook` once; Planner owns verify-plan, internal readiness, requirements coverage, requirements satisfaction, revision invalidation, and terminal package emission
6. `write-code-playbook`
7. independent execution verification using the plan package's commands and success criteria
8. PDI-owned retained-surface inspection against the approved outcome and real-path evidence
9. `verify-work` using parent-managed reviewer -> critic -> orchestrator-fix cycles

Every stage returns `PASS`, `GAPS`, `BLOCKED`, or `CAP_REACHED`.

- `PASS`: advance.
- `GAPS`: orchestrator fixes, increments the stage attempt, and delegates a fresh pass.
- `BLOCKED`: record exact unblock evidence and stop.
- `CAP_REACHED`: require continuation approval; never reinterpret it as PASS.

Do not invoke `verify-plan`, `requirements-coverage-gap-loop`, or `requirements-satisfaction-gap-loop` again downstream of Planner for the same plan. The research gates at stages 2-4 remain research-owned and are not plan gates.

## Planner Integration

Invoke canonical `plan-playbook` exactly once with `approval_context=CONVERGENCE` and the frozen outer state:

```text
--convergence-state "${XDG_STATE_HOME:-$HOME/.local/state}/kamen-convergence/<task-id>/state.json"
```

The enum alone is never authorization. The Planner controller derives and binds the immutable bounded authorization projection from that state. On a terminal verdict, call the canonical package boundary when a package exists, then use the generic adapter as the only bridge into outer stage state:

```text
python3 skills/plan-playbook/scripts/plan_package.py validate-package <task-root>
python3 skills/plan-playbook/scripts/plan_package.py stage-result <plan-state-json> --convergence-state "${XDG_STATE_HOME:-$HOME/.local/state}/kamen-convergence/<task-id>/state.json" [--package-directory <task-root>] --out <task-root>/plan-stage-result.json
python3 skills/_shared/convergence_state.py record-stage "${XDG_STATE_HOME:-$HOME/.local/state}/kamen-convergence/<task-id>/state.json" --result-file <task-root>/plan-stage-result.json
```

The adapter, not the caller, derives the outer task identity, next attempt, assigned requirement IDs, artifact identity, nested records, and gap lifecycle mapping. Pass its result file unchanged to the live `record-stage` command. For an inner PASS advancing prior outer plan blockers, reopen outer state and repeat adapter then `record-stage` through each adjacent successor until the adapter emits final PASS. Never assert a separate artifact ID, skip a blocker edge, or derive status from historical rather than latest dispositions.

`GAPS` leaves the current outer `plan` or prior `blocked` state unchanged. Ordinary `BLOCKED` and `CAP_REACHED` retain live `record-stage` behavior and do not transition to implementation.

## Plan Continuation Recovery

Only a SUBSTANTIAL inner plan capped at verify-plan iteration 10 is eligible. Derive continuation approval and operation IDs from task ID, outer iteration, plan attempt, capped inner-state hash, and plan hash. Freeze the authorization envelope's exact `outer_resume_status` and `outer_blocked_stage`, then resume from the first incomplete durable row:

1. Outer `status=cap_reached`, `cap_stage=plan`, no matching snapshot or approval: run `grant-plan-continuation`.
2. Matching approval is `granted` and outer state is the same cap: run `continue-stage`.
3. The approval is consumed, outer state equals its frozen direct `plan` or nested `blocked(plan)` return shape, and no valid inner approval/provenance exists: run `prepare-continuation-approval`.
4. Valid inner approval/provenance exists, outer state still equals that shape, and inner state remains eligible `CAP_REACHED`: run `continue-hardening`.
5. Outer approval is consumed, the inner continuation hash is bound, outer state still equals the frozen shape, and inner status is `HARDENING`: continuation is complete.

```text
python3 skills/_shared/convergence_state.py grant-plan-continuation <convergence-state> --id <continue-approval-id> --plan-package-id <package-id> --inner-state-sha256 <capped-inner-state-sha256> --plan-sha256 <plan-sha256> --approved-from-iteration 10 --approved-through-iteration 20 --approval-evidence <bounded-run-approval-evidence>
python3 skills/_shared/convergence_state.py continue-stage <convergence-state> --stage plan --approval-id <continue-approval-id> --operation-id <continue-operation-id>
python3 skills/plan-playbook/scripts/plan_package.py prepare-continuation-approval <plan-state-json> --convergence-state <convergence-state> --outer-approval-id <continue-approval-id> --outer-operation-id <continue-operation-id> --out <plan-run-root>/approvals/verify-plan-continuation-i10.json
python3 skills/plan-playbook/scripts/plan_package.py continue-hardening <plan-state-json> --approval <plan-run-root>/approvals/verify-plan-continuation-i10.json
```

`continue-stage` from ordinary `plan` or `blocked` is illegal. A consumed approval is never re-granted. Any changed return shape, hash, authorization, operation, partial provenance, state regression, or second continuation fails closed. `cap_from_status` restores direct caps to their prior stage and nested `blocked(plan)` caps to that exact blocked lifecycle without clearing its blocker metadata.

## Blocked PASS And Outer Resume

When inner PASS arrives while the outer lifecycle is blocked from plan, record and reopen state after each exact `open -> fixed-awaiting-verification -> verified -> closed` successor emitted by the adapter. Every edge must retain the validated package and plan identity.

Only after all mapped blockers are terminal, choose the sorted first closed mapped blocker as the resume anchor. Validate that the frozen outer authorization envelope permits resume for that anchor. Derive the resume approval and operation IDs from task ID, outer iteration, final plan attempt, anchor ID, and authorization-envelope hash, then use the live commands:

```text
python3 skills/_shared/convergence_state.py grant-approval <convergence-state> --id <resume-approval-id> --kind resume --operations '["resume"]' --target-ids '["<resume-anchor-blocker-id>"]' --repository-roots '[]' --allowed-paths '[]' --stage plan --evidence <authorization-envelope-path-and-sha256>
python3 skills/_shared/convergence_state.py resume <convergence-state> --stage plan --blocker-id <resume-anchor-blocker-id> --approval-id <resume-approval-id> --operation-id <resume-operation-id>
```

The replay matrix advances only the next incomplete adjacent edge. A direct PASS already in `plan` skips blocker successors and resume. A blocked plan with an open, fixed-awaiting-verification, or verified mapped blocker records only its next successor; terminal mapped blockers grant then resume when approval is absent, resume when the matching approval is granted, and proceed only when the matching operation is consumed. Any mismatched blocker, artifact, approval, operation, state, or skipped edge fails closed.

## Controller-Owned Implementation Authorization

Only after outer state is `plan`, recover the controller authorization from its current durable state:

- `NOT_REQUESTED`: prepare the deterministic request.
- `AWAITING_RESPONSE`: exact-replay request preparation if needed, then derive authorization from the frozen convergence state.
- `AUTHORIZED`: skip both producers and validate the existing receipt.

```text
python3 skills/plan-playbook/scripts/plan_package.py prepare-implementation-authorization <plan-state-json> --out <plan-run-root>/authorizations/implementation-request-r<revision>.json
python3 skills/plan-playbook/scripts/plan_package.py record-implementation-authorization <plan-state-json> --request <plan-run-root>/authorizations/implementation-request-r<revision>.json --convergence-state <convergence-state>
python3 skills/plan-playbook/scripts/plan_package.py validate-implementation-authorization <plan-state-json> --authorization <plan-run-root>/authorizations/implementation-r<revision>.json
python3 skills/_shared/convergence_state.py transition <convergence-state> --to implementation
```

This derives the same package-bound implementation receipt from the already approved outer authorization and never asks the user twice. A crash after request or receipt publication resumes from `show` and the fixed paths. Changed outer authorization, request, package, plan revision, scope, state, or receipt fails closed. Every implementation entry or resume reruns package and authorization validation. An outer state already transitioned to `implementation` returns success without invoking the inner authorization producers again.

## Review Loop

Review against the objective, hardened research, validated Planner package, all recorded diffs, runtime evidence, and every assigned requirement.

A gap finding shows correctness, coverage, contract alignment, runtime behavior, verification, or implementation completeness is not satisfied. Style, optional cleanup, and future improvements are non-gaps.

If any critic-validated gap remains, record it, increment the outer iteration, and return to research with the finding and violated requirement as first-class evidence. Stop only when independent review passes, every requirement is satisfied or explicitly excluded with approval, every gap or blocker is terminal, all required commands pass, and slot status is zero.

A review-driven plan change must use Planner `prepare-revision` and `record-revision`; it invalidates the emitted package and implementation authorization. Do not resume implementation until the successor completes all four owned plan stages on one hash, is emitted and package-validated, and receives a newly validated implementation receipt.

## Guardrails

- Preserve every source-edit baseline guard and the parent-only fixer/state-writer boundary.
- Preserve independent execution verification, review, and `verify-work`.
- Preserve default `commit_policy=none` and every G11 stop boundary.
- Do not create duplicate planning state, authorization state, plan gates, or user prompts.
- Do not transition the outer lifecycle to implementation before terminal package and implementation-authorization validation.
- Treat controller or adapter failures as fail-closed stage results, never as permission to reconstruct their decisions manually.

## Reporting

Lead with what now works and what it enables. Report closed gaps and raw verification evidence. Separate blockers from non-blocking notes. Never substitute stage or process labels for the practical result.
