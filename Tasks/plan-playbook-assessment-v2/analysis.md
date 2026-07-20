# Plan Playbook V2 Implementation Analysis

## Objective

Turn the approved Plan Playbook V2 research package into a bounded implementation that makes ordinary planning produce a grounded, decision-complete plan which can be implemented without a new product or design decision.

This task stops at an approved, independently hardened implementation plan. It does not change the live planning skill, install a candidate, promote a skill, commit, or push.

## Intake

- Task type: workflow/process, with implementation and promotion as downstream concerns.
- Task size: heavy. The change governs every future planning task and changes shared orchestration contracts.
- Repository grounding: `/Users/kamenkamenov/memory-knowledge`.
- Environment grounding: canonical source skills under `skills/` and managed Codex installation under `~/.codex/skills/`.
- Required plan verification: `verify-plan`, internal readiness, requirements coverage, and requirements satisfaction.
- Rollout requirement: local candidate installation and transactional canonical promotion only. There is no remote deployment.

## Approved Baseline

The immutable planning baseline is the controller-valid research package under `Tasks/plan-playbook-assessment-v2/research-package/`.

Its current-runtime result is:

- `R1_ROUTING_BOUNDARIES`: satisfied.
- `R2_EVIDENCE_GATE`: not satisfied.
- `R3_ONE_SHOT_COMPLETENESS`: not satisfied.
- `R4_HARDENING_INTEGRATION`: not satisfied.
- `R5_APPROVAL_CONTRACT`: not satisfied.
- `R6_EXECUTABLE_ORCHESTRATION`: not satisfied.
- `R7_PRACTICAL_EVIDENCE`: not satisfied.

The package therefore permits planning seven frozen obligations and does not permit adding unrelated planning features.

## Current-State Facts

### Canonical planning contract

`skills/plan-playbook/SKILL.md` is a prose-only contract. It correctly routes planning, preserves a research return path, and states the one-shot and locked-decision aims. It does not define:

- an evidence-sufficiency record;
- a required plan schema;
- deterministic lifecycle state;
- agent identity and close evidence;
- a shared retry or elapsed-time budget;
- a complete hardening order;
- machine-checkable terminal conditions;
- practical evaluation against downstream implementation clarification.

### Existing hardening components

The required components already exist and retain their ownership boundaries:

- `skills/verify-plan/` supplies the implementation-surface map, verification ledger, verifier, critic, and progressive coverage queue.
- `skills/doc-gap-closure-loop/` supplies internal document-readiness assessment.
- `skills/requirements-coverage-gap-loop/` supplies requirement breadth assessment.
- `skills/requirements-satisfaction-gap-loop/` supplies end-to-end depth assessment.
- `skills/_shared/STAGE_RESULT_CONTRACT.md` supplies `PASS`, `GAPS`, `BLOCKED`, and `CAP_REACHED` stage results.
- `skills/_shared/agent_slot_ledger.py` supplies reusable slot-lifecycle mechanics.

The stable implementation must orchestrate these components. It must not merge their responsibilities or rewrite them into one undifferentiated reviewer.

### Downstream consumers

Two current consumers must be reconciled with the canonical V2 lifecycle:

- `skills/task-workflow/SKILL.md` currently authors and hardens plans through its own size rules and direct `verify-plan` invocation. Without an integration change, it can bypass the canonical V2 gates.
- `skills/playbook-convergence-loop/SKILL.md` currently invokes `plan-playbook`, then separately invokes `verify-plan`, coverage, and satisfaction. Without an integration change, it duplicates most V2 stages and still omits plan internal readiness.

The stable boundary is for `plan-playbook` to own the complete planning lifecycle. Consumers invoke it once and consume its terminal receipt.

### Tests and installation

- `tests/test_skill_contracts.py` currently checks only broad playbook ordering and role-isolation phrases. It does not execute or evaluate planning behavior.
- The managed installer is `working-agreement/install_skills.py`; `working-agreement/INSTALL.md` explicitly forbids hand-copying installed skill directories.
- `skills/plan-playbook/SKILL.md` and `~/.codex/skills/plan-playbook/SKILL.md` are separate files, so source changes do not automatically update the installed skill.
- The research-playbook V2 implementation, evaluator, and transactional promotion scripts provide the proven local pattern for isolated candidate development and canonical replacement.

## Required Behavioral Contract

### Entry and evidence gate

Every invocation freezes an objective, atomic requirements, allowed repositories and paths, exclusions, approval context, plan profile, evidence roots, and budget before drafting.

There are exactly two valid entry modes:

1. `DIRECT`: every atomic requirement has a grounded evidence record and the controller validates evidence sufficiency.
2. `RESEARCH_PACKAGE`: the input is a controller-valid research package with terminal `PASS` and one `READY` record for every planner obligation. The research-package owner must expose a read-only `validate-package` boundary so planning consumes the original requirement schema without conversion or duplication.

If either entry mode cannot prove sufficient understanding, the planning run returns `BLOCKED` with `RESEARCH_REQUIRED`. It does not draft from an assumption and does not silently continue.

### Plan artifact

The plan must lock:

- scope and frozen requirements;
- current-state evidence;
- implementation surfaces and ownership;
- decisions and caller-visible contracts;
- ordered changes with exact paths and reasons;
- failure, resume, idempotency, and compatibility behavior;
- validation and acceptance criteria per requirement;
- approval, rollout, rollback, and out-of-scope boundaries;
- a terminal receipt tied to the final plan hash.

Either/or choices, optional in-scope work, unresolved operator choices, and hidden follow-up decisions are terminal blockers.

### Hardening lifecycle

The parent authors and edits the plan. Independent agents assess it in this order:

1. `verify-plan` verifier and critic.
2. Internal readiness.
3. Requirements coverage.
4. Requirements satisfaction.

Every role receives a controller-validated input-envelope file containing authoritative evidence but no producer rationale or hidden expected answer. The controller recomputes all referenced file/tree hashes and the raw output hash; caller-supplied digests are never accepted as proof. The verify-plan critic also receives the verifier's raw findings, as required for independent adjudication, but not verifier rationale or fixes. Verify-plan runs one or more verifier/critic pairs until its ledger has zero actionable findings and no unchecked high/medium coverage; verification iteration is globally monotonic across plan revisions and the ten-iteration cap is never replenished. The controller accepts monotonic same-revision ledger updates without treating them as plan revisions and deterministically renders the aggregate summary from validated records. Internal gate envelopes use the shared top-level stage-result fields but retain planning-owned nested finding/blocker records; a separate deterministic adapter maps the aggregate result into the exact live `convergence_state.py record-stage` schema. Any accepted plan or evidence-index edit preserves verification history and consumed budget but invalidates every prior stage PASS and starts a fresh full stage pass on the next global iteration.

### Proportionality

Both profiles run the complete lifecycle; proportionality changes artifact weight and budget, not which correctness questions are skipped.

- `LIGHT`: intake size `light` creates a provisional LIGHT run; the charter must name exactly one repository and `change_characteristics=["NONE"]`; the frozen set must contain exactly one requirement and at most three obligations; the draft must remain at most 200 UTF-8 `splitlines()` physical lines and at most 12 deterministically parsed Markdown heading units. Full response-sized artifacts for all four stages are persisted in `gate-results.json`. Maximum 2 plan rounds, 10 agent attempts, and 20 elapsed minutes.
- `SUBSTANTIAL`: intake size `standard|heavy`, or any LIGHT draft exceeding a LIGHT boundary, uses task-local ledgers and exact `.gap-audit.md`, `.coverage-audit.md`, and `.satisfaction-audit.md` artifacts. Maximum 3 plan rounds, 18 agent attempts, and 60 elapsed minutes. Profiles never downgrade.

Every attempt is reserved before spawn and consumes the shared budget. Slot evidence follows the live version-2 ledger lifecycle: recordable output closes and releases a bound slot, runtime failure closes and releases it, and spawn failure abandons and releases the unbound reservation. A role can be retried once. The same actionable-finding fingerprint in two consecutive rounds returns `CAP_REACHED`.

Artifact form is stage-specific: verify-plan is inline for both profiles; LIGHT keeps all three other full artifacts inline; SUBSTANTIAL owns the exact `.gap-audit.md`, `.coverage-audit.md`, and `.satisfaction-audit.md` files. Verify-plan provenance stores separate ordered verifier and critic input/output hashes.

### Approval behavior

An explicit planning request authorizes the bounded planning and hardening lifecycle; V2 does not ask whether to run its required gates.

After planning `PASS`:

- an ordinary task presents the granular change list, practical old-versus-new behavior, and cost once, then waits for implementation approval;
- an active `playbook-convergence-loop` consumes the plan receipt without asking again because the existing bounded authorization already covers approved-plan edits;
- every G11 stop boundary remains active for a new requirement, wider path, another repository, commit, deployment, destructive action, secret access, or external message.

## Recommended Implementation Shape

Build V2 as an isolated candidate at `skills/plan-playbook-v2/`, following the proven research-playbook candidate and promotion pattern.

The candidate should contain:

- the concise operator contract in `SKILL.md`;
- role and invocation metadata in `agents/openai.yaml`;
- reference contracts for entry/evidence, plan artifacts, hardening lifecycle, approval, and evaluation;
- a deterministic `scripts/plan_package.py` controller that owns frozen state, hashes, budgets, role attempts, stage results, invalidation, and terminal package validation.

Use `skills/verify-plan/scripts/verification_ledger.py` for implementation-surface coverage within the V2 controller. Do not expand that ledger into the overall orchestration state.

Develop and evaluate the candidate without changing canonical routing. Promote only after deterministic tests and fresh-agent practical evaluation pass.

## Practical Evaluation Boundary

The evaluator must use the exact historical artifacts identified by evidence E10-E14 as immutable fixture sources. E10 maps to the small case, E11-E13 map to the substantial case, and E14 plus the approved research package map to the evidence-uncertain initial/resume case. It must create labeled cases for:

- a small grounded plan;
- a substantial multi-surface plan;
- an evidence-uncertain request that must pause for research.

For small and substantial legacy and V2 plans, a fresh downstream implementation agent receives a run-owned snapshot of the recorded plan/package, the bounded source roots used in the practical workflow, and a case-neutral answer-free output schema: no original request, planner public contract, research package, hidden gold, expected IDs, evaluator code, or producer rationale. Single-agent rows use fresh normal agents; each candidate planner row is a logical parent-orchestrated harness invocation with a fresh draft producer and the real independent hardening lifecycle. The live shared slot ledger records every inner agent, and the evaluator records every implementer-consulted source under frozen roots. The evidence-uncertain V2 path first records `BLOCKED/RESEARCH_REQUIRED`, then resumes the same controller state with the prepared research package and passes only that resumed package to the downstream implementer. The fixed matrix contains 13 logical rows. The evaluator scores positive grounded implementation and verification actions rather than absence-only self-report:

- requirement preservation;
- implementation anchors;
- verification anchors;
- decision completeness;
- zero downstream clarification;
- no scope or evidence invention.

Free-form model preference and self-reported quality booleans are not acceptance evidence. The fixture public contract exposes canonical requirement, obligation, and negative-boundary IDs without selected answers; hidden gold supplies critical sets, forbidden claims, and expected transitions. The scorer uses locked numerator/denominator formulas, rejects empty denominators, micro-aggregates each arm, and applies typed thresholds only to V2 while retaining legacy as the informational baseline. Downstream implementer rows remain waiting until their recorded planner output is validated and materialized into a hashed input envelope.

## Promotion Boundary

Promotion must be transactionally restart-safe and reversible:

1. Validate a locked evaluator score and source-tree hashes.
2. Back up canonical source, candidate source, managed manifest, tests, evaluator, all changed consumer sources, and all affected installed directories with restorable bytes and hashes.
3. Preserve the old canonical skill as a legacy fixture.
4. Rewrite the candidate alias and metadata to canonical `plan-playbook`.
5. Atomically replace canonical source, remove the candidate alias, and install canonical `_shared`, `plan-playbook`, `research-playbook`, `task-workflow`, and `playbook-convergence-loop` together through `working-agreement/install_skills.py`.
6. Verify all five source/installed tree-hash pairs, contract tests, candidate absence, and a fresh canonical invocation.
7. Journal and fsync every mutation/command phase, recover at every command entry, and roll back and re-hash every promotion-owned path if apply, validation, live probing, final verification, or process restart fails; an external live-agent failure must call the deterministic abort command before control returns.
8. Freeze and compare the presence/tree hash of every managed installed projection while never overwriting an unrelated path that changed outside promotion ownership.

## Risks and Containment

- Scope inflation: contain implementation to the seven frozen obligations and the two confirmed consumer integrations.
- Reviewer duplication: keep the four stages distinct and ordered; do not make one agent impersonate multiple gates.
- Stale PASS results: tie every stage result to one canonical plan hash and invalidate all stages after an edit.
- Hidden bypass: test direct planning, task-workflow, and convergence-loop entry paths.
- Gold leakage: keep expected evaluator predicates outside agent-visible fixtures.
- Installed/source drift: candidate evaluation installs the candidate plus the backward-compatible research validator and shared slot uniqueness fix; promotion installs all five changed managed skills transactionally and compares every source/installed tree hash.
- Approval drift: encode ordinary and pre-authorized paths separately and test every G11 stop boundary.

## Resolved Decisions

- V2 is developed as an isolated explicit-only candidate and promoted transactionally.
- The canonical `plan-playbook` owns the full planning lifecycle after promotion.
- All plans run all four assessment stages; size changes budgets and artifact form only.
- The parent is the only plan and state writer.
- Any plan edit requires a complete fresh rerun.
- Practical promotion evidence includes a fresh downstream implementer outcome, not only plan self-assessment.
- No directive change, remote deployment, commit, or push is part of this implementation plan.

## Remaining Unknowns

None require a user decision before implementation planning. Exact controller field names and CLI options are specified in `plan.md` and must be implemented exactly rather than inferred during coding.
