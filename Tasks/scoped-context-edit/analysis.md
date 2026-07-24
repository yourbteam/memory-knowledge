## Objective

Replace repeated, brittle exact-context repository edits with one cataloged operational sequence that prepares a current receipt, requires one small `apply_patch`, invalidates stale context, verifies the permitted change surface, and can be discovered and reused through the canonical sequence registry.

## Task Type And Size

- Type: workflow/process implementation
- Size: standard
- Active mode chain: Plan -> Write code -> Review

## Current-State Facts

- No registered sequence currently matches guarded exact-context semantic edits.
- Repeated manual edits have failed mechanically because anchors changed between inspection and patching, patches contained too much surrounding text, shell quoting altered intended text, or a command interface was reconstructed instead of inspected.
- `apply_patch` remains the required semantic edit mechanism; the reusable automation must guard it rather than replace it with a second write path.
- `scripts/discovery_bootstrap.py` accepts a complete version-1 candidate specification and atomically creates, selects, activates, and starts a governed discovery run.
- `operations/sequences/discovery-promotion-lifecycle/sequence.md` is the canonical path for two current-bundle qualifications, atomic promotion, blocker/successor handling, and registered same-path verification.
- Repository tests must run through `scripts/run_pytest.sh`.
- The worktree already contains unrelated user changes. This task must preserve them and detect changes outside its explicitly allowed paths instead of requiring a clean tree.

## Stable Boundary

The stable fix is a repository-aware, read-only guard around the authoritative edit boundary:

1. inspect and uniquely identify the literal anchor;
2. seal the target and current worktree state in a tamper-evident receipt;
3. prove the receipt is still current immediately before one small `apply_patch`;
4. require an explicit `cancel` and fresh `prepare` after a rejected patch; an intervening edit invalidates currentness automatically;
5. verify required and forbidden postconditions, outside-scope stability, and that no new `git diff --check` defect was introduced.

The guard will never translate alternate output shapes, guess anchors, or write the semantic change itself. It can prove the sealed preimage and final scope, but it cannot observe the editing tool or count tool invocations. Therefore one small `apply_patch` is an explicit operational constraint in the registered sequence, while the receipt enforces the before/after state. A failed currentness check or rejected patch requires cancellation and a fresh preparation receipt.

## Scope

- Add `scripts/context_edit_guard.py`.
- Add focused tests in `tests/test_context_edit_guard.py`.
- Add task artifacts under `Tasks/scoped-context-edit/`.
- Bootstrap one governed discovery candidate and dependency manifest.
- Drive that exact bundle through the existing promotion lifecycle until registered verification passes.
- Allow only lifecycle-generated updates under `operations/sequences/` and `operations/work-memory/events.jsonl`.

## Out Of Scope

- Refactoring existing sequence controllers or work-memory contracts.
- Changing the required `apply_patch` editing rule.
- Cleaning or rewriting unrelated worktree changes.
- Committing, pushing, deploying, or changing remote state.
- Resuming the broader sequence-flywheel implementation before this omission is closed.

## Risks And Controls

- Dirty-worktree false positives: separately seal HEAD, index entries, working-tree bytes, missing tracked files, and untracked bytes; compare post-edit changes to that baseline.
- Path escape: accept only repository-relative regular files resolved beneath the repository root.
- Receipt tampering: hash a canonical receipt payload and fail closed on mismatch.
- Stale context: compare the target digest and full baseline immediately before the patch; require an authenticated checked receipt at verification and consume it on success or cancellation.
- Pre-existing whitespace defects: fingerprint allowed-path `git diff --check` diagnostics by path, message, and offending-line hash, then reject only new diagnostic fingerprints.
- Secret exposure: do not persist target contents or literal assertion values in the receipt; reject secret-bearing operational use in the sequence instructions.
- Registry drift: create the registered folder and catalog row only through the existing atomic promoter.

## Acceptance Outcome

On a future exact-context edit, `sequence-runner` can find `scoped-context-edit` from the registry use condition and then select it explicitly; the operator runs prepare and currentness checks, applies one bounded patch, and runs verification. A stale anchor, intervening write, out-of-scope change, newly introduced malformed diff, or failed postcondition stops the sequence with a specific non-zero diagnostic. The sequence is not complete until two same-bundle discovery runs and one registered same-path run have passed.
