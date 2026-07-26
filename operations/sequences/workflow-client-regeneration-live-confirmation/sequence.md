# workflow-client-regeneration-live-confirmation

<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->
## Operator entry point

After selecting and activating this registered sequence, launch the shared controller with no
arguments:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
<!-- END SEMANTIC INTAKE ENTRYPOINT -->

## Use When

A United Partners workflow must be regenerated from a pinned parent run with the owner's
controlled-topic policy set supplied, so every flagged interview answer is governed by an explicit
owner ruling before any claim can reach a draft.

Use `workflow-resume-from-phase-live-confirmation` instead when a persisted run must continue from
its exact first unfinished phase. That sequence resumes; this one regenerates.

## Outcome

Regenerate a United Partners workflow from a pinned parent run, bind every flagged interview answer
one-to-one to an owner handling policy, stream the structured watcher feed, and end at completion or
the first persisted deviation.

## Required Inputs

- A pinned parent run whose recorded inputs this regeneration builds on.
- A run whose recorded client answers the regeneration reuses.
- An owner-authored controlled-topic policy set covering every flagged answer. Each policy binds to
  exactly one flagged answer, and every flagged answer must be covered; the join fails closed as
  `policy_source_excerpt_not_preserved` otherwise.
- The machine repository-roots authority at `~/.config/memory-knowledge/repositories.json`
  must map `united-partners` to the real United Partners repository before selecting this
  cross-repository sequence.
- The managed Python runtime and command-backed role adapter for live execution.
- Write authority for the client's persisted state directory.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| preflight-regeneration-driver | env PYTHONPATH=src /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --help | The driver exposes --controlled-topic-policies-file alongside --parent-run and --answers-from-run. | Run in the united-partners repository with the existing managed Python runtime. |
| dry-run-policy-binding | env PYTHONPATH=src /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --client <client> --parent-run <parent-run-id> --answers-from-run <answers-run-id> --controlled-topic-policies-file <policy-path> --dry-run | The controlled-topic join completes and every flagged answer binds to exactly one policy. | No model calls. Run this before spending a live regeneration; a policy set that fails to bind stops at phase 5. |
| regenerate-with-owner-policies | env PYTHONPATH=src 'UP_HARNESS_AGENT_COMMAND=/Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/codex_role_command.py' UP_HARNESS_AGENT_MAX_ATTEMPTS=3 UP_HARNESS_AGENT_TIMEOUT_SECONDS=600 UP_HARNESS_CODEX_TIMEOUT_SECONDS=600 /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --client <client> --parent-run <parent-run-id> --answers-from-run <answers-run-id> --controlled-topic-policies-file <policy-path> | A child run regenerates under the owner policy set, streams watcher activity, and reaches completion or one persisted diagnosable deviation. | The driver validates the workflow identity and boundary before model work and launches scripts/watch_run.py automatically. |
| verify-automation | env -C /Users/kamenkamenov/united-partners PYTHONPATH=src /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests.unit.test_client_regeneration_resume tests.unit.test_workflow_resume tests.unit.test_vivacom_phase20_reproduction -v | The owner-input routes, resume boundary, and captured Phase 20 correction path pass their deterministic regression suites. | The command binds its own united-partners working directory; no model call is made. |

## Failure Handling

Fail before model work when the parent run is missing, the answers source is missing, or the policy
file is absent, unreadable, or not a JSON array. During execution, retain the child state and stop
at the first persisted deviation; catalog and correct that stable boundary before another live
successor.

A `policy_source_excerpt_not_preserved` block at `join-controlled-topic-policies` means the supplied
policy set does not bind one-to-one to the flagged answers: a policy quotes text that is not in any
flagged answer, two policies claim the same answer, or a flagged answer has no policy. Correct the
policy set — never the excerpt — because the excerpt is the client's own recorded words.

## Verification

Pass signal: The controlled-topic join binds every flagged answer to exactly one owner policy, the
regeneration proceeds past the controlled-topic gate, and the run reaches completion or one
persisted diagnosable deviation while watcher telemetry remains active.

Registered 2026-07-26 after the driver gained `--controlled-topic-policies-file`. Before that flag
existed the workflow's all-FLAG policy set could not be supplied through any registered route: the
engine read `inputs.controlled_topic_policies`, but across 97 recorded run state files the key had
never once been present. Run a fresh registered same-path verification before treating prior
evidence as current-bundle proof.
