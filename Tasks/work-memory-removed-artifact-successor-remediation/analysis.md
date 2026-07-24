# Work-Memory Removed-Artifact Successor Remediation

## Objective

Repair the correction-bound successor contract that prevents verification when a changed file is intentionally removed from the exact corrected source bundle and its out-of-bundle bytes later change.

## Scope

In scope:

- `scripts/work_memory.py::_validate_successor_corrections`
- focused successor-selection and run-start tests in `tests/test_work_memory.py`
- same-path retry of correction `95b2539a-557e-4195-90ad-7cabd963408e`

Out of scope:

- event-schema changes
- physical deletion of a changed file from the repository
- carrying an unverified removal through a later bundle transition
- unrelated work-memory prevention and observer changes already present in the worktree

## Confirmed Failure

Correction event `187f398a-9e21-4290-aa02-262c208ae0e6` records `operations/blockers/BLOCKERS.md` at hash `8edcac...` and correction ID `95b2539a...`. Bundle transition `4576958a-0abc-47cf-9eba-4175b40b9d9a` removes that path and commits exact successor bundle `496cc313...`. The correction's own blocker transition then regenerates the generated view. Successor selection rejects the now-different out-of-bundle bytes with `successor-correction-artifact-hash-mismatch`.

## Cause Chain

1. **Symptom:** a required correction-bound successor cannot be selected.
2. **Immediate cause:** `_validate_successor_corrections` re-hashes every changed artifact unconditionally after it has already accepted the correction transition's exact `new_bundle_hash`.
3. **Upstream producer:** `cmd_correct` records both the complete new source-bundle hash and correction-time hashes for every drifted path. Those hashes are valid historical evidence.
4. **Downstream consumer:** successor selection and run-start call the same validator. They incorrectly turn historical evidence for an intentionally excluded path into a continuing filesystem invariant.
5. **Stable boundary:** the correction-produced source bundle is authoritative for post-correction membership; live-byte checks apply only to changed artifacts retained in that bundle.

Confidence is confirmed by controller code, focused tests, immutable events 3032-3035, and an independent assessment-only agent.

## Stable Contract

For each changed artifact:

- **Retained in the effective successor bundle:** require repository-root availability and exact raw-byte equality with `changed_artifact_hashes` at both selection and run-start.
- **Absent from the effective successor bundle but present in the predecessor bundle:** accept it only when the correction transition's `new_bundle_hash` exactly equals the effective successor bundle. Do not inspect its current out-of-bundle bytes.
- **Absent from both effective and predecessor bundles:** reject as `successor-correction-artifact-outside-bundle`.
- **Correction transition hash differs from the effective bundle:** preserve the existing carried-correction rule. Every changed artifact must still be retained and raw-hash matched. An earlier removal therefore remains fail-closed and requires an explicit superseding correction.

This fixes the authority conflict without weakening tamper detection for any file the successor will execute or otherwise trust.

## Required Verification

1. Strengthen the exact-bundle removed-artifact test by mutating the excluded file after correction recording; selection must pass.
2. Add run-start coverage proving further mutation of that excluded file does not invalidate the already-selected exact bundle.
3. Preserve existing failures for retained-file byte changes, selection-to-start tampering, an artifact absent from both bundles, and a removed artifact carried across a later bundle hash.
4. Retry the original correction-bound selection and start as the same-path confirmation.

## Worktree Constraint

`scripts/work_memory.py`, `tests/test_work_memory.py`, and `tests/test_work_memory_bootstrap.py` already contain unrelated uncommitted work. The remediation must edit only the removed-artifact branch and its focused tests and must not reformat, revert, or absorb those changes.
