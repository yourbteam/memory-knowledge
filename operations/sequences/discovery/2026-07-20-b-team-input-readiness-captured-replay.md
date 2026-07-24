# Sequence Discovery Log: b-team-input-readiness-captured-replay

DiscoveryId: discovery-abeb7493-9f8d-5ec2-a5b2-d59c3b463b69
Status: discovery
CreatedAtUtc: 2026-07-20T10:02:58Z
RegisteredSequenceMatch: none

## Intended Outcome

Replay the captured B-Team validate-input-readiness phase through the real phase-ledger manager and external model adapter, streaming role activity and persisting ordered verifier/critic history.

## Why This Looks Repeatable

Phase-ledger convergence defects must be diagnosed at the captured phase boundary before paying for another complete CD-S-002 workflow run.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| run-captured-readiness-replay | env PYTHONPATH=/Users/kamenkamenov/united-partners/src UP_HARNESS_AGENT_COMMAND='/Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 /Users/kamenkamenov/united-partners/scripts/codex_role_command.py' UP_HARNESS_AGENT_MAX_ATTEMPTS=3 UP_HARNESS_AGENT_TIMEOUT_SECONDS=600 UP_HARNESS_CODEX_TIMEOUT_SECONDS=600 /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -c 'import json; from dataclasses import replace; from pathlib import Path; from up_harness.phase_ledger.executor import CommandRoleExecutor; from up_harness.phase_ledger.manager import run_phase_ledger_loop; state=json.loads(Path("/Users/kamenkamenov/united-partners/Tasks/bteam-corporate-demo/state/up-run-91492279665b.json").read_text()); sink=lambda event: print("[activity] "+json.dumps({"replay_id":"bteam-readiness-20260720","phase_id":"validate-input-readiness",**event},sort_keys=True),flush=True); executor=replace(CommandRoleExecutor.from_env(),activity_sink=sink); result=run_phase_ledger_loop(phase_id="validate-input-readiness",phase_contract_path="up-strategy-input-readiness-contract.md",source_text=state["context"]["source_packet"],executor=executor,max_loops=3); payload={"source_run_id":state["run_id"],"phase_id":"validate-input-readiness","ledger":result.ledger}; Path("/private/tmp/up-run-91492279665b-input-readiness-replay.json").write_text(json.dumps(payload,indent=2)); assert result.ledger["verifier_history"], "verifier_history_missing"; assert all("patch_outcomes" in entry for entry in result.ledger["critic_history"]), "critic_patch_outcomes_missing"; print(json.dumps({"status":result.ledger["status"],"verifier_history_count":len(result.ledger["verifier_history"]),"critic_history_count":len(result.ledger["critic_history"]),"final_findings":result.ledger["verifier"]["findings"],"output_path":"/private/tmp/up-run-91492279665b-input-readiness-replay.json"},indent=2))' | A real same-code-path phase result plus complete ordered verifier/critic history is persisted for root-cause inspection. | Uses the exact source_packet captured in up-run-91492279665b; streams command-executor attempt activity and does not run upstream or downstream workflow phases. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

TBD while discovering.

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
