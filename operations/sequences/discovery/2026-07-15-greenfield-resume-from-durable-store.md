# Sequence Discovery Log: greenfield-resume-from-durable-store

DiscoveryId: discovery-716f268a-2a6b-50ce-9ded-1619b092ce0c
Status: discovery
CreatedAtUtc: 2026-07-15T07:04:50Z
RegisteredSequenceMatch: none

## Intended Outcome

Resume a halted multi-feature greenfield N3 program after a container recreate wiped the ephemeral /tmp state, reconstructing every needed input from the DURABLE stores (origin/main merged code, lakmus-runtime task branches, MK runs/prompts) and resuming the DAG onto the merged base with parallelism — no re-drive of merged features.

## Why This Looks Repeatable

Every engine-change re-drive recreates the container; until the new durable-program-state code has driven a program from scratch, any pre-durability program (feat-8 supermariobros) needs this cross-store recovery to resume, and future partial-loss recoveries will follow the same steps.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| S11 PREREQ docker/colima must be up before the drive | colima start; docker info | First drive attempt died at preflight FAIL docker is not running. Docker here runs via colima (unix .colima/default/docker.sock); the VM had stopped. colima start brought docker back (ServerVersion 29.5.2), then the drive re-launched. | PROMOTE: the greenfield-full-drive preflight should auto-start colima or print colima start on this exact failure. |
| S10 FINAL drive command (clean slate) | greenfield_m1_empty_repo_verify.sh reset THEN greenfield_full_drive.sh --repo thebteambg/supermariobros --spec /Users/kamenkamenov/Downloads/BT-000023-build-react-super-mario-bros-clone-prep-2026-06-30.json | reset already done (main README-only). Full drive builds image (durable-resume + review-convergence + wave-width on main), recreates container with the env widths, seeds auth, N1 auto-chains N2 to N3 onto main with parallelism. |  |
| S9 parallelism at all levels (env-driven) | env-file WORKFLOW_GREENFIELD_HARVEST_WIDTH=5 + WORKFLOW_GREENFIELD_WAVE_WIDTH=5; commit e8fbeb23 makes the N2 seam pass parallelWidth=GREENFIELD_WAVE_WIDTH | Harvest fan-out AND N3 feature-DAG waves both parallel (cap 5, capacity-aware). Full-drive path needs NO --parallel-width flag; the env drives both. review fan-out concurrency 4 default. | Fixed a real gap: the auto-chained N3 was hardcoded serial before e8fbeb23. |
| S8 clean-slate reset + fresh drive commands | greenfield_m1_empty_repo_verify.sh reset THEN greenfield_full_drive.sh --repo thebteambg/supermariobros --spec DOWNLOADS_JSON --branch main --parallel-width 5 (GREENFIELD_HARVEST_WIDTH=5 in env-file) | reset strips main to README-only via git orphan force-push (gh token); full drive rebuilds image (carries durable-resume + review-convergence fix) + recreates container + seeds auth + N1 to N2 to N3 with parallelism. |  |
| S7 ingestion path is the greenfield eval which parses the raw JSON | greenfield_asset_decode.decode_assets; mcp_server.py 12592-12627 N1 on_terminal | The N1 eval parses the raw butler JSON as the spec, decodes+writes+commits+pushes 26 assets into public/assets, and the chain consumes job.description. Feed the raw JSON via --prompt-file; no rendered spec, no separate asset upload. |  |
| S6 canonical super-mario input JSON located and repo verified | docs/supermario-input-fitness-research.md line 4; python3 json read job.git_repo | SOURCE = /Users/kamenkamenov/Downloads/BT-000023-build-react-super-mario-bros-clone-prep-2026-06-30.json (565236 bytes, DURABLE in Downloads). job.git_repo = https://github.com/thebteambg/supermariobros CORRECT. Carries job.description whole-game prompt + 26 base64 assets (25 png sprite/level + 1 midi). | This one file triggers a clean run AND re-creates the assets. Keep it; it is the canonical greenfield input. |
| S5 the DECOMPOSITION itself is durable but the engine cannot consume it on resume | mawf_get_prompt 36f3c460 -> original_prompt_ref repo://Tasks/mawf-task-f1a4f04d.../initial-prompt.txt | Each of the 13 feature tasks has its initial-prompt.txt on its lakmus-runtime task branch; the decomposition (feature set + order recoverable from run timestamps) IS durable. BUT the new durable-resume engine only resumes from a program-state.json (never written for this old run) and refuses to fabricate one -> it has NO path to reconstruct a program from the existing durable MK tasks. | FORK: (A) recover whole-game prompt + re-run N1->N2 (re-decompose; alignment risk); (B) engine change to reconstruct program-state from the durable MK feature tasks (grounded, no re-decompose, no misalignment). The whole-game program prompt is NOT one of the 13 feature prompts; it lives in the intake/N1 store (not yet located). |
| S4 parallelism knobs at every level | grep parallel/concurrency greenfield_drive_dag.py mcp_server.py review-workflow.yaml | --parallel-width 5 (wave, cap 5) + GREENFIELD_HARVEST_WIDTH=5 (N2 harvest, via --env-file, default 1) + review fan-out concurrency:4 / GREENFIELD_FANOUT_WIDTH=4 default + capacity-aware auto-cap | harvest width is the ~1hr step; env-file has no width vars yet |
| S2 map durable stores surviving container recreate | git ls-remote supermariobros + lakmus-runtime; mawf_list_tasks/list_workflow_runs | CODE=origin/main supermariobros (9 features, full tree); LEDGERS=task/<id> on yourbteam/lakmus-runtime; RUNS+tasks+prompts=MK (project 348d4957, each feature task has prompt_id+task_artifact_branch); GONE(=/tmp): universe, n3-ready ckpt, program status, merge-progress, the spec file | whole-game spec /tmp/rtm_mini4_spec.json gone from disk -> recover from MK prompt/intake store |
| S1 durable-resume does NOT rescue pre-durability program | git show 51b0bee5; read gf-n3-resume-durability-plan.md:13,767 | CONFIRMED: refuses to fabricate program-state (LEGACY_CHECKPOINT_NOT_DURABLE); forward-durable only | halted program must be resumed by reconstructing inputs from durable stores + fresh N1->N2 |

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
