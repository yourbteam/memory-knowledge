# Work-Memory Removed-Artifact Successor Plan

## Goal

Allow a correction-bound successor to verify the exact correction-produced bundle when a changed path was intentionally excluded from that bundle and its out-of-bundle bytes later changed, without weakening checks for retained artifacts or later bundle transitions.

## Frozen Decisions

- The bundle transition's exact `new_bundle_hash` is the authority for post-correction membership.
- Correction-time raw hashes remain historical evidence for excluded paths, not continuing runtime dependencies.
- Retained changed paths remain raw-byte bound at selection and run-start.
- A removed path cannot be carried through a later bundle hash; the existing explicit-supersession policy remains.
- Event schemas and persisted historical events do not change.
- Existing unrelated worktree changes are preserved byte-for-byte outside the named edit regions.

## Change 1: Correct Successor Validation

File: `scripts/work_memory.py`

In `_validate_successor_corrections`:

1. Compute whether each correction transition's `new_bundle_hash` exactly equals the effective successor bundle hash.
2. Preserve the existing carried-correction fallback when hashes differ: every changed artifact must be present in the effective bundle and its raw bytes must still match.
3. In the final artifact loop, classify the artifact by membership:
   - present in the effective bundle: require repository-root availability and exact raw-byte hash;
   - absent from the effective bundle but present in the predecessor bundle: accept only for the exact correction-produced bundle, then skip filesystem rebinding;
   - absent from both bundles: retain `successor-correction-artifact-outside-bundle`.
4. Keep the same function as the shared authority for both `cmd_select` and `cmd_run_start`.

Reason: the current unconditional raw read duplicates bundle authority and makes intentional dependency removal unverifiable after an unrelated generator rewrites the excluded file.

## Change 2: Harden Focused Contract Tests

File: `tests/test_work_memory.py`

1. Strengthen `test_successor_selection_accepts_an_explicitly_removed_bundle_artifact` by changing the excluded file after the correction hash is recorded and before selection. Selection must still bind the exact corrected bundle.
2. Add a run-start test that:
   - selects the exact correction-produced bundle with an explicitly removed artifact;
   - changes the excluded file again after selection;
   - retains the existing synthetic mocks for bundle resolution, ledger reads, registry access, and task-local receipt/root paths;
   - invokes the real `cmd_run_start` and `_validate_successor_corrections` path without mocking the validator;
   - additionally mocks the final `transact` persistence edge only to capture the emitted event;
   - verifies that event retains the exact predecessor run ID, correction IDs, and selected source-bundle hash.
3. Retain and run the existing negative tests for:
   - later-bundle removal rejection;
   - retained-file mutation before selection;
   - artifact absence from both predecessor and successor bundles;
   - retained-file mutation between selection and run-start.

Reason: the tests must prove the authority split directly and prevent the fix from becoming a broad exemption from tamper checking.

## Verification

1. Run the focused successor-selection and run-start tests through `scripts/run_pytest.sh`.
2. Run the complete `tests/test_work_memory.py` and `tests/test_work_memory_bootstrap.py` files through the same wrapper to detect interaction with the pre-existing worktree changes.
3. Retry selection for correction `95b2539a-557e-4195-90ad-7cabd963408e` against predecessor `d54fa050-89ff-5b90-86b8-825c1e62f261`.
4. Start that selected successor and record same-path verification before closing blocker `blk-687d42d9d2286a9d20fbae4a`.
5. Resume the paused verify-plan coverage remediation only after the correction-bound successor starts successfully.

## Completion Criteria

- Exact-bundle removal survives excluded-file regeneration at selection and run-start.
- Retained-file tampering still fails at both boundaries.
- Removed artifacts still fail across later bundle hashes unless explicitly superseded.
- Focused and full work-memory test files pass.
- The original correction-bound successor selects and starts through the real controller path.
- No unrelated code, tests, events, or generated views are reverted or rewritten by the implementation patch.
