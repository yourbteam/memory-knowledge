---
name: plan-playbook
description: Use when a goal must become a controller-bound, decision-complete implementation plan before code is written. Freeze grounded evidence, require the behavioral boundary matrix, and harden one plan revision through verify-plan plus independent internal-readiness, requirements-coverage, and requirements-satisfaction lenses. Do not use for open-ended research, code changes, or diff review.
---

# Plan Playbook

Produce a controller-bound plan package that a competent implementer can execute without rediscovery, unstated choices, or a second planning pass.

## Before planning

1. Freeze the charter: objective, repositories, allowed paths, supplied-input root, exclusions, deliverables, approval boundaries, and change characteristics.
2. Select exactly one entry mode from [entry-and-evidence.md](references/entry-and-evidence.md): `DIRECT` or `RESEARCH_PACKAGE`.
3. Require grounded evidence for every requirement and non-empty implementation and verification anchors for every planner obligation. Insufficient evidence returns `BLOCKED/RESEARCH_REQUIRED`; do not draft around it.
4. Derive the deterministic task root described in [entry-and-evidence.md](references/entry-and-evidence.md), or use an existing caller-owned task root when one was explicitly supplied.
5. Initialize the controller with that exact existing task root. The controller owns state, hashes, snapshots, attempts, findings, stage records, package emission, and authorization receipts.
6. The canonical controller root is `<task-root>/.plan-playbook/`. When an existing task has only `<task-root>/.plan-playbook-v2/`, run `plan_package.py migrate-run-root --task-directory <task-root>` once before continuing. Never alias or dual-read the legacy root. The migration fails closed while an attempt, revision, emission transaction, blocked-state resume, or capped continuation is in flight; finish that operation with the legacy controller first.

## Ownership

The parent orchestrator is the only writer of plan text, surface maps, decisions, ledgers, findings dispositions, revisions, and task artifacts. Delegated agents are assessment-only and must be fresh, independently bound, and closed through the shared slot ledger.

Never collapse a required role into the parent. Missing spawn, wait, close, or slot capability returns `BLOCKED`.

The parent must invoke this playbook directly; never delegate the whole planning run to a
subagent. A task-intake, ownership, evidence, controller, or runtime `BLOCKED` result returns only
the blocked state and required resolution. It must not include draft plan content. Downstream
evaluation and implementation may consume only an emitted package whose current controller state
and canonical validation both establish terminal `PASS`.

## Build the plan

Create the exact package inputs in [plan-package.md](references/plan-package.md). The plan must:

- preserve every frozen requirement and exclusion;
- make every in-scope decision and reject unresolved either/or, optional, or operator-choice language;
- map each requirement and obligation to concrete files, entry points, contracts, implementation steps, and verification steps;
- state practical before/after consequences and bounded implementation and verification cost;
- contain no implementation work and no review-stage work.

Before drafting, complete the repository preflight and behavioral-boundary inventory required by
[entry-and-evidence.md](references/entry-and-evidence.md). A claimed existing file, fixture,
symbol, parser behavior, consumer, or verification command that was not confirmed from frozen
source is missing evidence, not an implementer detail.

Record the draft through the controller as one same-revision set. Do not edit controller snapshots or emitted package files directly.

## Harden in fixed order

Follow [hardening-lifecycle.md](references/hardening-lifecycle.md) exactly:

1. `VERIFY_PLAN`
2. `INTERNAL_READINESS`
3. `REQUIREMENTS_COVERAGE`
4. `REQUIREMENTS_SATISFACTION`

The three later stages use the immutable contract `PLAN_PLAYBOOK_V2_HARDENING_LENSES_V1` in [hardening-lenses.md](references/hardening-lenses.md). Each runs in a different fresh subagent against the same plan hash and lens-contract hash. A PASS from one lens never satisfies another.

Only the parent applies accepted fixes. Any plan revision invalidates all prior stage PASS results and restarts hardening at the next globally monotonic verify-plan iteration. Preserve consumed attempts and elapsed time.

## Profiles and bounds

- `LIGHT`: provisional `light` intake, one repository, `change_characteristics=["NONE"]`, one requirement, at most three obligations, at most 200 physical lines, and at most 12 deterministic document units. Maximum 3 rounds, 10 prepared agent attempts, and 20 minutes.
- `SUBSTANTIAL`: `standard|heavy` intake or any LIGHT predicate violation. Maximum 3 rounds, 23 prepared attempts, and 60 minutes. One approved iteration-10 continuation raises the limits to 43 attempts and 120 minutes; it does not reset history.
- An expired SUBSTANTIAL revision may receive one ordinary, controller-bound continuation tranche. Each exact approval adds 60 minutes and three hardening rounds, preserves all attempts, revisions, findings, and global verify-plan iteration numbering, and is single-use for that revision. A later recorded revision may request its own tranche; the same revision cannot repeat one or combine it with the iteration-10 continuation.
- If an ordinary SUBSTANTIAL revision reaches the shared attempt cap immediately after a successful verifier because the final three attempts are reserved for the owned lenses, one exact, state-bound approval may add only the missing paired-critic attempt. It is single-use for that revision, preserves the three owned-lens reservations, and is ineligible at every other lifecycle position.
- If a corrected ordinary SUBSTANTIAL revision has no attempts yet because its prior-revision critic consumed the last verify-plan capacity, one exact, state-bound approval may add exactly the next verifier/critic pair. The request must bind that prior critic's GAPS output to fully applied finding transitions and the changed plan hash. It is single-use for the corrected revision and preserves the three owned-lens reservations.

Reserve one attempt for each owned lens. Each role permits one retry. Repeated actionable-finding fingerprints, exhausted attempts, elapsed-time expiry, or the verify-plan iteration limit return `CAP_REACHED`, never PASS. Profiles only escalate.

## Terminal behavior

- `PASS`: all four ordered stages pass on one current plan hash; the three owned lenses also bind one lens-contract hash; every agent slot is released; package emission and canonical validation succeed.
- `GAPS`: actionable findings require a parent-owned revision and a complete fresh hardening run.
- `BLOCKED`: name the missing evidence, research return, runtime capability, or approval boundary. Do not emit a PASS package.
- `CAP_REACHED`: name the exact exhausted cap. Do not reinterpret it as success.

After PASS, follow [approval-and-routing.md](references/approval-and-routing.md). Ordinary use presents one package-bound granular implementation request with practical consequence and cost. Authorized convergence derives the same durable implementation receipt from its frozen outer authorization without asking twice. Neither path may enter Write Code until the controller validates the current package and authorization receipt.

The comparison contract formerly stored in `references/evaluation.md` is historical promotion evidence, not a runtime planning gate. Secrets, commits, pushes, deployments, and external messages retain their separate approval boundaries.
