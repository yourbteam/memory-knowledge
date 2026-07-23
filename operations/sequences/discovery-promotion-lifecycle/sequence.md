# discovery-promotion-lifecycle

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

Promote a governed discovery sequence through two same-bundle qualifications, atomic registration, and registered same-path verification.

## Outcome

Drive a discovery lineage through readiness, atomic promotion, and registered same-path verification with deterministic blocker and successor handling.

## Required Inputs

- A discovery document and dependency manifest already governed by `work_memory.py`.
- A unique target sequence id, registry use condition, operation kind, automation display, and pass signal.
- One exact `verify-automation` command in the discovery command table; placeholders are rejected for this verification command.
- Repository-root mappings when the target bundle spans repositories.
- Permission to update the memory-knowledge registry, ledger, blocker view, discovery metadata, and registered sequence folder.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| status | python3 scripts/discovery_promotion_lifecycle.py status --file <discovery-log> --sequence-id <sequence-id> --repo-roots-file <repo-roots-file> | verified | Return exactly one lifecycle stage from ledger and bundle state. |
| drive | python3 scripts/discovery_promotion_lifecycle.py drive --file <discovery-log> --sequence-id <sequence-id> --use-when <use-when> --operation-kind <operation-kind> --automation-display <automation-display> --pass-signal <pass-signal> --repo-roots-file <repo-roots-file> | verified | Qualify the same bundle twice, atomically promote it, and same-path verify the registered bundle without reconstructing commands. |
| correct | python3 scripts/discovery_promotion_lifecycle.py correct --file <discovery-log> --sequence-id <sequence-id> --task-id <failed-run-task-id> --solution <solution> --changed-artifacts-file <manifest> --reusable-behavior-changed <yes-or-no> --repo-roots-file <repo-roots-file> | verified | Bind the complete bundle-drift manifest to one open blocker, transition it to awaiting verification, close the failed run, and make successor verification the next stage. The task id is required when a protected controller changes. |
| correct-superseding | python3 scripts/discovery_promotion_lifecycle.py correct --file <discovery-log> --sequence-id <sequence-id> --solution <solution> --changed-artifacts-file <manifest> --reusable-behavior-changed <yes-or-no> --supersedes-correction-id <correction-id> --repo-roots-file <repo-roots-file> | verified | Replace a stale correction, transition its prior blocker to superseded, and make only the new correction eligible for successor verification. |
| correct-registered | python3 scripts/discovery_promotion_lifecycle.py correct-registered --subject-id <sequence-id> --task-id <failed-run-task-id> --solution <solution> --changed-artifacts-file <manifest> --reusable-behavior-changed <yes-or-no> --repo-roots-file <repo-roots-file> | verified | Atomically bind a registered-verification defect to the complete registered-bundle drift, transition its blocker, close the failed run, and require its corrected-bundle successor before completion. Repeating the same correction after an interrupted response is idempotent. |
| correct-registered-superseding | python3 scripts/discovery_promotion_lifecycle.py correct-registered --subject-id <sequence-id> --solution <solution> --changed-artifacts-file <manifest> --reusable-behavior-changed <yes-or-no> --supersedes-correction-id <correction-id> --repo-roots-file <repo-roots-file> | verified | Atomically replace a stale registered correction, terminalize its prior blocker, close the failed run, and require only the replacement correction's successor. |
| protected-correct | python3 scripts/work_memory_bootstrap_launcher.py correct | verified | The controller automatically uses the immutable launcher to execute the activated old bootstrap snapshot as `python3 scripts/work_memory_bootstrap.py correct` when `work_memory.py`, the lifecycle controller, or the bootstrap changes; operators do not reconstruct its arguments. |
| verify-automation | scripts/run_pytest.sh tests/test_discovery_promotion_lifecycle.py tests/test_sequence_discovery_log.py tests/test_sequence_promote.py tests/test_work_memory.py tests/test_work_memory_bootstrap.py tests/test_blocker_catalog.py tests/test_sequence_guard.py | passed | Exercise lifecycle routing, fail-closed cataloging, discovery readiness, atomic promotion, complete bundle-drift enforcement, sealed correction execution, authenticated bootstrap upgrades, ledger rules, blocker transitions, and command guarding through the repository-mandated test runner. |

## Failure Handling

- If a guarded discovery verification fails, the controller catalogs the blocker against the exact active run and stops with its blocker, occurrence, and run identities. It does not retry.
- Apply the stable boundary fix, include every old-to-current bundle drift artifact in the changed-artifact manifest, then invoke `correct` or `correct-registered`. The ledger rejects partial or extra manifests. Protected controller changes run through the activated sealed bootstrap. One transaction records the correction and bundle transition, moves the blocker to `fixed-awaiting-verification`, terminalizes superseded blockers, and closes the failed run. A retry after an interrupted response returns the same correction.
- If a successor fails, its new open blocker takes precedence over every older pending correction. Correct the new blocker and explicitly supersede stale correction ids before another successor can run.
- The bootstrap launcher is the immutable trust anchor and is intentionally outside automatic self-upgrade. Any launcher drift fails closed as `immutable-bootstrap-launcher-change` and requires an explicitly versioned trust-anchor migration, not an improvised correction.
- The next `drive` must select a corrected-bundle successor. A normal selection is rejected while a correction awaits verification.
- A successful successor records same-path verification against the exact blocker and correction, then transitions the blocker through `verified` to `closed` before closing the run passed.
- Any bundle change resets qualification evidence. The controller obtains two fresh passed same-path runs on the new hash before promotion.
- Promotion uses the journaled atomic promoter. A crash is recovered by the promoter before any retry; target drift or recovery conflict fails closed.
- Registered blocker and pending-correction state takes precedence over any earlier passing proof. Registered verification runs against the promoted bundle and is required before the controller reports `complete`.

## Verification

- The focused suite covers deterministic stage routing, placeholder rejection, two-run qualification routing, automatic failure cataloging, correction-required stop behavior, readiness metadata invariance, atomic promotion recovery, work-memory successor rules, blocker transitions, and sequence guarding.
- The controller will drive this discovery through its own two qualifying runs, promotion, and registered verification before it is used for `commit-push-main`.

Pass signal: The controller returns stage complete after a passed registered same-path run.

Promoted from `2026-07-15-discovery-promotion-lifecycle`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
