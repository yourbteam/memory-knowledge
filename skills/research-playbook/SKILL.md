---
name: research-playbook
description: Use when research is intended to feed an implementation plan and must produce a build-bound, planner-ready package through a bounded independent-subagent workflow. Freeze scope and requirement maturity, run a core researcher plus internal-readiness, requirements-coverage, and requirements-satisfaction lenses on identical evidence, adjudicate findings, and emit a concise handoff for a fresh one-shot implementation planner. Do not use for implementation planning, code changes, or diff review.
---

# Research Playbook

Produce a planner-ready research package without allowing the research stage to absorb planning or implementation decisions. The parent orchestrator owns all state and artifact writes. Core research, the three lenses, and adjudication must run through independent subagents.

## Required Runtime

Require parent-level subagent spawn, wait, and close tools. Stop with `BLOCKED` when those tools are unavailable. Do not merge researcher, lens, adjudicator, or fixer roles as a fallback.

Use the runtime's slot-lifecycle contract for every subagent. Retain role, runtime-agent ID, input-envelope hash, output hash, attempt number, completion evidence, close evidence, and release state. Close every runtime agent and require zero active slots at round boundaries.

## Fixed Workflow

1. **Freeze the charter.** Record the objective, in-scope questions, exclusions, authoritative roots, deliverables, budget, requirements, maturity, and the canonical JSON `research_value_type` for every atomic requirement. Read [charter-and-maturity.md](references/charter-and-maturity.md). A post-freeze scope change returns `BLOCKED` without mutating the charter.
2. **Run core research.** Spawn a fresh assessment-only researcher with the frozen envelope and raw evidence. Exclude producer rationale, hidden answers, prior conversational reasoning, and prior agent explanations. The researcher returns a structured draft using the exact candidate `requirement_statuses` schema in [planner-handoff.md](references/planner-handoff.md); it does not edit files.
3. **Materialize the candidate.** The parent validates the response, records hashes and agent evidence, and writes the candidate package through `scripts/research_package.py`. Candidate and envelope hashes use the controller's named canonical-JSON hash contract, not ordinary file-byte SHA-256.
4. **Run the three lenses concurrently.** Spawn one fresh assessment-only subagent per lens. Each receives the identical candidate and frozen-envelope hash, the named hash contract, and the exact controller command that verifies both JSON payloads. It cannot see another lens's output. Across the three outputs, every candidate-declared `material_gaps` ID must be emitted for explicit adjudication rather than disappearing in an empty PASS result. Each lens returns one terminal JSON object with exactly `verdict` and `findings`; pass that object unchanged to `record-lens --terminal-envelope`. A lens returns `PASS` when no further research-stage work is required, even when it emits planner-owned findings; use the exact envelope, finding schema, and verdict mapping in [lenses-and-findings.md](references/lenses-and-findings.md).
5. **Adjudicate independently.** Spawn a fresh assessment-only adjudicator with the frozen charter, candidate, and raw lens findings. It classifies, deduplicates, and proposes dispositions; it does not fix the candidate.
6. **Apply accepted research fixes.** The parent alone applies `FIX_IN_RESEARCH` findings and records terminal or carried findings. Never apply a planning, scope, approval, or implementation decision as a research edit.
7. **Run a fresh full round.** Any candidate edit requires a new core researcher, all three lenses on one new identical hash, and a fresh adjudicator. A partial rerun cannot return `PASS`.
8. **Prove planner readiness and emit the handoff.** Build the exact evidence index and one structured readiness record for every planner obligation as defined in [planner-handoff.md](references/planner-handoff.md). The parent verifies that every anchor, owner, required input, closure condition, and evidence ID is grounded. On valid `PASS`, supply both JSON inputs to `emit-package` and write the six-file research package. Missing implementation anchors inside accessible frozen roots returns `GAPS`; an unavailable evidence route or unnamed approval boundary required for planning returns `BLOCKED`.

## Shared Budget

Enforce structural budgets across the whole run and a time budget per individual `(round, role)` task:

- maximum 3 candidate rounds;
- maximum 15 total agent spawn attempts;
- maximum 60 minutes for each individual task, shared by its initial attempt and one retry;
- at most 1 retry for a failed role;
- every attempted spawn consumes the attempt budget;
- 2 consecutive rounds with the same actionable-finding fingerprint return `CAP_REACHED`.

A complete round uses one core researcher, three independent lenses, and one adjudicator. Spawn or output failure leaves the round incomplete. An incomplete round cannot pass.
Total workflow elapsed time is informational and may exceed 60 minutes; it never terminalizes an otherwise bounded run.

## Terminal Rules

Return `PASS` only when all of these are true:

- all three lenses returned `PASS` for the same candidate and frozen-envelope hash;
- the fresh adjudicator found no actionable research finding;
- every blocker is terminal and every carried planning item has a grounded handoff disposition;
- every planner obligation has a controller-validated `READY` record;
- no scope or maturity changed after freeze;
- the package hashes and agent lifecycle evidence validate;
- the package satisfies the planner-handoff contract.

Return `GAPS` when research-actionable findings remain, `BLOCKED` when required accessible evidence or approval is unavailable, and `CAP_REACHED` when any shared cap or repeated-fingerprint rule fires. Missing runtime evidence for a `FUTURE_SYSTEM` requirement is an evidence limitation, not a blocker by itself.

## Boundaries

- Do not write implementation plans or code.
- Do not ask the user to approve gates after this skill was explicitly invoked; invocation authorizes the bounded research workflow only.
- Do not expose gold fixtures or expected answers to research, lens, adjudicator, or planner agents.
- Do not claim one-shot readiness from document quality alone. Coverage and maturity-aware satisfaction must pass.

The comparison record in [evaluation.md](references/evaluation.md) is historical promotion evidence, not a runtime gate.
