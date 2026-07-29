# Sequence Discovery Log: hot-overlay-src-into-running-container

DiscoveryId: discovery-3215af47-5817-5f5f-9ecc-1bf287038035
Status: discovery
CreatedAtUtc: 2026-07-25T18:45:45Z
RegisteredSequenceMatch: none

## Intended Outcome

Deploy changed workflow_orch source into the ALREADY-RUNNING local container (no image rebuild, no recreate — durable program state must survive) and prove the new code is actually live, not served from a stale .pyc

## Why This Looks Repeatable

Every engine fix during a halted greenfield drive needs this: recreate wipes credentials + program state (that is greenfield-recreate-resume's job), and a full image rebuild costs ~20min. Stale __pycache__ has silently served OLD code twice this session, making a deployed fix look like it did nothing.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| 0. Preflight: container healthy AND no active producers before restarting | docker ps --filter name=workflow-orch-local-sequence-check | Up 4 hours (healthy); producer count 0 -> safe to restart | NEVER restart while a drive is running. CLI quirk: append-step rejects a command containing Go-template braces or a shell pipe as invalid-command-row; keep the recorded command brace-free and pipe-free. |
| 4. VERIFICATION GATE: assert the new symbols in the RUNNING interpreter | docker exec <container> /app/.venv/bin/python -c 'import inspect; ...assert new params/constants...' | 6/6 green: work_branch_override present, validator correct both ways, STATIC_DOD_FIX_ATTEMPTS=2, work_branch_pin threaded, engine reads the pin | Use /app/.venv/bin/python — the container's default python3 lacks yaml (server runs 'uv run python -m workflow_orch.mcp_server'). A health-200 alone does NOT prove the new code loaded; assert the symbols. |
| 3. Restart (state survives; do NOT recreate) | docker restart <container>; until curl -sf http://localhost:18083/health >/dev/null; do sleep 2; done | health {"status":"ok"} | Recreate would wipe credentials + program state -> that is greenfield-recreate-resume's job, not this one. |
| 2. MANDATORY: clear stale bytecode | docker exec <container> sh -c 'find /app/src -name "__pycache__" -type d -prune -exec rm -rf {} +' | pycache cleared | THE trap. Skipping this silently serves the OLD code after restart; it cost two false 'the fix did nothing' diagnoses on 2026-07-24/25. |
| 1. Copy ONLY the changed modules | docker cp src/workflow_orch/<file>.py <container>:/app/src/workflow_orch/<file>.py | 3 files copied | Narrow overlay, not a whole-tree copy: a dirty tree would otherwise ship unrelated WIP. |
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
