# Sequence Discovery Log: proactive-sequence-observer-requirements-research

DiscoveryId: discovery-8119b46b-2c71-5bf9-b6eb-1727df716b34
Status: discovery
CreatedAtUtc: 2026-07-16T11:28:08Z
BootstrapRequestSha256: 152767973be05063f2ff31251759f2daba6a0160fa0b8782dac79e08ca017a42
RegisteredSequenceMatch: none

## Intended Outcome

Produce one immutable, evidence-grounded, planner-ready six-file requirements research package for a proactive sequence observer without writing an implementation plan or code.

## Why This Looks Repeatable

Future feature requirements must repeatedly use the same bounded core-research, three-lens, adjudication, and planner-readiness packaging path instead of ad hoc prose.

## Required Inputs, Auth, Or Environment

- A frozen observer charter and atomic future-system requirements
- Repository-local evidence from the existing sequence discovery, guard, promotion, registry, blocker, and work-memory machinery
- Fresh assessment-only core researcher, three independent lenses, and adjudicator outputs

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| initialize-package | python3 skills/research-playbook/scripts/research_package.py init <state-json> --charter <charter-json> --requirements <requirements-json> --operational-maturity FUTURE_SYSTEM --evidence-availability <evidence-availability-json> | Immutable research charter and requirements state initialized. | Evidence availability is a JSON input file; no scope or maturity changes are permitted after this step. |
| initialize-agent-slots | python3 skills/_shared/agent_slot_ledger.py init <slot-ledger-json> --max 3 | A bounded three-slot lifecycle ledger is initialized before any research agent is spawned. | Acquire before spawn, bind the runtime agent id, then mark completed and closed before release; retry any role at most once. |
| hash-agent-input | python3 skills/research-playbook/scripts/research_package.py hash-json <json-file> | Canonical JSON identity returned for the candidate or envelope. | Use canonical_json_sha256, not the file-byte hash, as the package identity. |
| record-core-candidate | python3 skills/research-playbook/scripts/research_package.py record-candidate <state-json> --candidate <candidate-json> --envelope <envelope-json> --evidence-availability <evidence-availability-json> | The complete core candidate and identical lens envelope are validated and recorded. | Evidence availability is a JSON input file; every frozen requirement must have one exact typed requirement_statuses record. |
| record-agent-attempt | python3 skills/research-playbook/scripts/research_package.py record-attempt <state-json> --runtime-agent-id <agent-id> --role <role> --round <round> --candidate-hash <candidate-hash> --input-envelope-hash <envelope-hash> --status <SUCCEEDED-or-FAILED> --output-hash <output-hash> --slot-closed --close-evidence <close-evidence-json> | One bounded role attempt and runtime closure are recorded before any successful terminal envelope for that role. | The status is the controller enum SUCCEEDED or FAILED; record the closed successful attempt before record-lens or record-adjudication. |
| record-lens | python3 skills/research-playbook/scripts/research_package.py record-lens <state-json> --round <round> --lens <lens> --runtime-agent-id <agent-id> --candidate-hash <candidate-hash> --envelope-hash <envelope-hash> --terminal-envelope <terminal-envelope-json> | One unchanged terminal lens envelope is recorded after its successful closed attempt. | Run for internal readiness, requirements coverage, and requirements satisfaction on the identical candidate. |
| record-adjudication | python3 skills/research-playbook/scripts/research_package.py record-adjudication <state-json> --round <round> --runtime-agent-id <agent-id> --candidate-hash <candidate-hash> --envelope-hash <envelope-hash> --adjudications <adjudications-json> | All raw findings are classified without the adjudicator editing the candidate. | Only FIX_IN_RESEARCH can cause a new complete research round. |
| emit-package | python3 skills/research-playbook/scripts/research_package.py emit-package <state-json> <output-directory> --research <research-md> --evidence-index <evidence-index-json> --planner-readiness <planner-readiness-json> --planner-handoff <planner-handoff-md> | Exactly six planner-ready package files are emitted with validated hashes. | The output directory must not already exist. The package is requirements research only; no implementation plan or code is produced. |
| show-final-state | python3 skills/research-playbook/scripts/research_package.py show <state-json> | Terminal verdict, budget, hashes, requirements, and agent lifecycle evidence are visible. | PASS requires all three lenses and adjudication to be terminal on one candidate hash. |

## Failure Handling

Stop on post-freeze scope or maturity drift; retry a failed agent role at most once with the identical input hash; after any candidate edit start one complete fresh round; return BLOCKED for unavailable required evidence or an unnamed approval boundary; do not modify sequence runtime code, directives, schemas, deployments, or external systems.

## Verified Path

- The controller emits exactly six files only after every requirement has grounded evidence, a typed conclusion, planner-ready anchors, three PASS lenses on one candidate hash, and a fresh adjudicator with no research-actionable finding.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
