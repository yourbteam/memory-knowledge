# Planner v2 Step 7 Blockers

## SGAP-001 Ordinary Authorization Is Not Durable

- Status: VERIFIED/CLOSED
- Requirements: R5_APPROVAL_CONTRACT, R6_EXECUTABLE_ORCHESTRATION
- Practical consequence: an ordinary task-workflow run can interpret a valid
  plan package as permission to begin implementation even though G11 requires
  an explicit, bounded implementation approval.
- Historical evidence: current task-workflow proceeds autonomously after
  hardening at `skills/task-workflow/SKILL.md:18-22,179-185`; the pre-fix plan
  snapshot `.verify-plan/snapshots/plan/55fdf0a7c4d7cae5d0ecda16602b074189722cd7d773669912e82f57201ec414.md:580-586`
  validated the package while only convergence authorization was persisted at
  the same snapshot's lines `161-163`.
- Stable boundary: a canonical ordinary implementation-authorization receipt
  must bind package and plan identity, repositories, allowed paths, granular
  changes, consequence, cost, and approval evidence. Task-workflow must block,
  resume, replay, and fail closed through that receipt.
- Verification required: direct, denial, resume, replay, tamper, drift, and
  no-duplicate-convergence approval tests plus a fresh end-to-end R5/R6 trace.
- Solution: `plan.md` now defines deterministic post-emission request,
  request-specific confirmation, ordinary/convergence authorization sources,
  canonical receipt/state fields, task-workflow wait/resume enforcement, and
  convergence receipt validation before transition to implementation.
- Changed artifact: `Tasks/plan-playbook-assessment-v2/plan.md` at SHA-256
  `1d770a88cac46583ad4a5e43f245b3e5eb2075888adb7316c2ad4e1cdc169ee8`.
- Verification evidence: fresh Cycle 2 satisfaction traced G11 through the
  current task-workflow consumer and the planned request, raw-response,
  controller-derived receipt, restart, replay, drift, and convergence reuse
  boundaries at `plan.md:362-383,490-500,595-639`. All eight R5/R6 depth
  lenses passed; `plan.satisfaction-audit.md` records the no-edit PASS.

## SGAP-002 Evaluator Gold Is Self-Authorable

- Status: VERIFIED/CLOSED
- Requirement: R7_PRACTICAL_EVIDENCE
- Practical consequence: an evaluator implementation can choose easy fixture
  requests or hidden gold that the candidate naturally passes; hashing those
  bytes proves only later immutability, not representative correctness.
- Historical evidence: E10 and E14 contain real defects, but the pre-fix plan
  snapshot `.verify-plan/snapshots/plan/55fdf0a7c4d7cae5d0ecda16602b074189722cd7d773669912e82f57201ec414.md:624-642,681-689`
  defined only fixture/gold schemas and did not lock exact requests,
  requirements, boundaries, forbidden claims, expected transitions,
  implementation roots, or source derivation for every value.
- Stable boundary: create an independently reviewed, source-derived fixture
  authority before candidate execution and bind its identity through prepare,
  row recording, scoring, score validation, promotion, and verification.
- Verification required: every fixture/gold field traces to E10-E14 evidence;
  weakened or substituted requests, IDs, boundaries, transitions, roots, or
  gold fail closed; then a fresh full R7 depth trace passes.
- Solution: `plan.md` now requires a pre-candidate source-derived authority,
  one-to-one value derivations, a fresh independent reviewer lifecycle and
  receipt, generated fixture projections, and authority/review hash binding
  through prepare, score, score validation, promotion, verify, and tests.
- Changed artifact: `Tasks/plan-playbook-assessment-v2/plan.md` at SHA-256
  `1d770a88cac46583ad4a5e43f245b3e5eb2075888adb7316c2ad4e1cdc169ee8`.
- Verification evidence: fresh Cycle 2 satisfaction traced E10-E14 through
  source derivations, exact nested review schemas, parent-derived reviewer
  identity, the 13-row evaluator, scoring, replay, and promotion at
  `plan.md:650-672,702-715,946-955`. All eight R7 depth lenses passed;
  `plan.satisfaction-audit.md` records the no-edit PASS.
