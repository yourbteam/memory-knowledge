# Sequence Discovery Log: mawf-playbook-test-sequences

Status: discovery
CreatedAtUtc: 2026-06-27T06:57:46Z
RegisteredSequenceMatch: none

## Intended Outcome

Two registered test sequences (Full all-gates, Speed skip-gates) driving the 4-playbook chain with stop-on-blocker + convergence-loop + blast-radius re-entry

## Why This Looks Repeatable

Every engine/config fix must be re-validated by driving the 4-playbook chain to completion; this is the standing test harness, run repeatedly per blocker

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| Discrete-action driver: gates STOP and need explicit answer-gate (both policies) | answer-gate --gate-policy full|speed at each gap-closure gate (pending-approvals shows the waiting runId/phaseId) | Verified: ea359be9 (dark-factory/full) ran research to ask-run-research-gap-closure and STOPPED (pending-approvals). The operator dark-factory auto-loop only auto-resolves gates while the start polling process is alive; with discrete actions it dies between calls, so the gate waits. answer-gate full (control approve) -> issues/yes -> research-gap-closure runs. So Full=explicit approve, Speed=explicit reject; chain-mode secondary | Corrected Full doc + driver docstring (had wrongly said dark-factory auto-runs with no answer-gate) |
| Fix continuation primitive: continuation-start was wrong; use resume->playbook-continuation-select | _fetch_decision: playbook-start --selected-task-action resume (queries workflow.playbook.state) -> decisionType; continue acts only on playbook_continuation_selection; repair on playbook_repair_required | Proven in 2026-06-22 discovery log. continuation-start is the precode review-handoff path (wrong); it spawned a spurious failed research re-run (3e66d60c, scope-research failed) that polluted the MAWF state and masked the real success (3db63137). decision fetch now returns the correct decision. continue/repair need --repo + --branch (NO_PROJECT_CONTEXT / CODE_PROJECT_BRANCH_REQUIRED) | Recovery: clean start_over with corrected driver. resume is read-only (does not spawn). Added decision subcommand |
| Chain-mode is the Full/Speed lever (grounded in approve_run/reject_run) | CHAIN_MODE_FOR_POLICY: full->dark-factory, speed->manual-handoff | Verified: dark-factory research run auto-ran research-gap-closure (gate recorded decision=ISSUES answer=yes). workflow_engine.approve_run:9404 defaults auto-approve to issues_answers[0]=yes=RUN; reject_run:9436 maps reject to clean_answers[0]=no=SKIP. So dark-factory deterministically runs gates (Full); manual-handoff stops gates for explicit reject (Speed). Asymmetric by mechanics, not preference | Full needs NO answer-gate (gates auto-run); Speed answer-gate rejects at each stop. Both need approve-start + continue. Driver+docs updated |
| Add mandatory dark-factory chain-start approval (approve-start) | scripts/mawf_playbook_test_sequence.py approve-start --task-guid <t> --workflow-name <wf> --run-id <run> | Dark-factory creates each workflow run in waiting_approval (decisionType playbook_approval_required, all phases pending) until control-approve. Policy-independent (full+speed both approve). Distinct from optional gap-closure gate. Verified: approve on research run 3db63137 -> running 1, phases began executing | _classify now returns waiting_start_approval for playbook_approval_required; docs' per-workflow flow updated to approve-start -> poll -> answer-gate -> continue |
| Fix AUTH_CONFIG_CONFLICT on first live start | driver runs operator from --operator-cwd (default /private/tmp), never repo root | Root cause: operator reads Path.cwd()/.env as fallback auth; repo-root .env carries WORKFLOW_ORCH_USER_EMAIL/TOKEN_KEY which collide with the JWT secret. Fix: _operator runs with cwd=neutral dir + fail-closed guard if that dir has a .env | Fingerprint: errorCode AUTH_CONFIG_CONFLICT / 'WORKFLOW_ORCH_JWT_SECRET cannot be combined with token-key auth'. Matches the proven manual pattern (cd /private/tmp before run.sh) |
| Author + register 3 sequences | operations/sequences/{mawf-playbook-full-test,mawf-playbook-speed-test,mawf-playbook-blocker-reentry}/sequence.md + SEQUENCES.md rows | directive read + sequence_guard activate + guard all pass; real answer-gate/start/reenter commands guard green via single-line shapes | Promote: stable command shapes, inputs, failure handling (blocker-reentry), and verification recorded |
| Author shared driver | scripts/mawf_playbook_test_sequence.py (gate-policy full|speed; infra/start/poll/answer-gate/continue/repair/reenter/record-blocker) | ruff clean; --help + dry-run command shapes correct; answer-gate maps full->approve speed->reject for the 2 optional gates, no-op for write-code/review | Grounded OPTIONAL_GATES from workflow YAMLs; decision-envelope JSON shape from 2026-06-24 verification log |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
