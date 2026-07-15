# Sequence Discovery Log: discovery promotion lifecycle
ReadyAtUtc: 2026-07-15T07:35:43Z

DiscoveryId: discovery-b6658d35-7870-5d15-9f4b-d316138cec83
Status: promoted
PromotedSequenceId: discovery-promotion-lifecycle
CreatedAtUtc: 2026-07-15T07:19:14Z
RegisteredSequenceMatch: none

## Intended Outcome

Drive a discovery lineage through readiness, atomic promotion, and registered same-path verification with deterministic blocker and successor handling.

## Why This Looks Repeatable

Every newly discovered operational sequence must traverse this lifecycle before it can be safely reused from the canonical registry.

## Required Inputs, Auth, Or Environment

- A discovery document and dependency manifest already governed by `work_memory.py`.
- A unique target sequence id, registry use condition, operation kind, automation display, and pass signal.
- One exact `verify-automation` command in the discovery command table; placeholders are rejected for this verification command.
- Repository-root mappings when the target bundle spans repositories.
- Permission to update the memory-knowledge registry, ledger, blocker view, discovery metadata, and registered sequence folder.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| status | python3 scripts/discovery_promotion_lifecycle.py status --file <discovery-log> --sequence-id <sequence-id> --repo-roots-file <repo-roots-file> | verified | Return exactly one lifecycle stage from ledger and bundle state. |
| drive | python3 scripts/discovery_promotion_lifecycle.py drive --file <discovery-log> --sequence-id <sequence-id> --use-when <use-when> --operation-kind <operation-kind> --automation-display <automation-display> --pass-signal <pass-signal> --repo-roots-file <repo-roots-file> | verified | Qualify the same bundle twice, atomically promote it, and same-path verify the registered bundle without reconstructing commands. |
| correct | python3 scripts/discovery_promotion_lifecycle.py correct --file <discovery-log> --sequence-id <sequence-id> --solution <solution> --changed-artifacts-file <manifest> --reusable-behavior-changed <yes-or-no> --repo-roots-file <repo-roots-file> | verified | Bind the complete artifact manifest to one open blocker, transition it to awaiting verification, close the failed run, and make successor verification the next stage. |
| correct-superseding | python3 scripts/discovery_promotion_lifecycle.py correct --file <discovery-log> --sequence-id <sequence-id> --solution <solution> --changed-artifacts-file <manifest> --reusable-behavior-changed <yes-or-no> --supersedes-correction-id <correction-id> --repo-roots-file <repo-roots-file> | verified | Replace a stale correction, transition its prior blocker to superseded, and make only the new correction eligible for successor verification. |
| correct-registered | python3 scripts/discovery_promotion_lifecycle.py correct-registered --subject-id <sequence-id> --solution <solution> --changed-artifacts-file <manifest> --reusable-behavior-changed <yes-or-no> | verified | Bind a registered-verification defect to the registered bundle and require its corrected-bundle successor before completion. |
| correct-registered-superseding | python3 scripts/discovery_promotion_lifecycle.py correct-registered --subject-id <sequence-id> --solution <solution> --changed-artifacts-file <manifest> --reusable-behavior-changed <yes-or-no> --supersedes-correction-id <correction-id> | verified | Replace a stale registered correction, terminalize its prior blocker, and require only the replacement correction's successor. |
| verify-automation | uv run pytest tests/test_discovery_promotion_lifecycle.py tests/test_sequence_discovery_log.py tests/test_sequence_promote.py tests/test_work_memory.py tests/test_blocker_catalog.py tests/test_sequence_guard.py | passed | Exercise lifecycle routing, fail-closed cataloging, discovery readiness, atomic promotion, ledger rules, blocker transitions, and command guarding. |

## Failure Handling

- If a guarded discovery verification fails, the controller catalogs the blocker against the exact active run and stops with its blocker, occurrence, and run identities. It does not retry.
- Apply the stable boundary fix, ensure every changed artifact is present in the discovery dependency manifest, then invoke `correct`. The controller records the correction, moves the blocker to `fixed-awaiting-verification`, and closes the failed run.
- The next `drive` must select a corrected-bundle successor. A normal selection is rejected while a correction awaits verification.
- A successful successor records same-path verification against the exact blocker and correction, then transitions the blocker through `verified` to `closed` before closing the run passed.
- Any bundle change resets qualification evidence. The controller obtains two fresh passed same-path runs on the new hash before promotion.
- Promotion uses the journaled atomic promoter. A crash is recovered by the promoter before any retry; target drift or recovery conflict fails closed.
- Registered verification runs against the promoted bundle and is required before the controller reports `complete`.

## Verified Path

- The focused suite covers deterministic stage routing, placeholder rejection, two-run qualification routing, automatic failure cataloging, correction-required stop behavior, readiness metadata invariance, atomic promotion recovery, work-memory successor rules, blocker transitions, and sequence guarding.
- The controller will drive this discovery through its own two qualifying runs, promotion, and registered verification before it is used for `commit-push-main`.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
