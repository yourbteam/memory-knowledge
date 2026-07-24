## Goal

Implement and promote one reusable `scoped-context-edit` sequence without changing unrelated code or bypassing the repository's existing discovery-to-promotion contracts.

## Approved Change Plan

### 1. Add the read-only edit guard

- File: `scripts/context_edit_guard.py`
- Implement these exact command shapes:
  - `prepare --repo-root <absolute-or-relative-repo> --target <repo-relative-file> --anchor <literal> --anchor-count <positive-int> --receipt <absolute-path-outside-repo> --allow <repo-relative-path> [--allow ...] [--require-after <literal> ...] [--forbid-after <literal> ...]`
  - `check --receipt <absolute-path-outside-repo>`
  - `verify --receipt <absolute-path-outside-repo>`
  - `cancel --receipt <absolute-path-outside-repo>`
  - `self-check`
- Reject absolute or escaping target/allow values, non-regular targets, a target outside every allowed prefix, receipt paths inside the repository, empty assertions, non-positive anchor counts, and non-unique anchor counts. Repeated `--allow`, `--require-after`, and `--forbid-after` options are ordered input arrays and duplicate values are invalid.
- Persist canonical JSON with `schema_version`, `state`, canonical repository root, target, sorted allowed paths, target SHA-256, HEAD identity, complete index-entry hash, tracked/untracked working-file identity map, missing tracked paths, anchor count/hash, required/forbidden byte-length-plus-SHA-256 assertions, baseline whitespace-diagnostic fingerprints, and `receipt_sha256`. Do not persist target, anchor, or assertion contents. Authenticate `receipt_sha256` before every transition.
- `prepare` may create a new receipt or replace only an authenticated terminal `cancelled`/`verified` receipt. It emits `SCOPED CONTEXT EDIT PREPARED` and exits zero; a validation/guard rejection exits 3, while `argparse` usage errors retain exit 2.
- `check` requires `state=prepared`, proves HEAD, index, working bytes, missing tracked paths, untracked paths, and target SHA are unchanged, atomically transitions to `state=checked`, and emits `SCOPED CONTEXT EDIT CURRENT`. An idempotent retry is allowed only while the baseline is still current.
- `verify` requires an authenticated `state=checked` receipt, requires the target digest to differ, enforces required/forbidden assertions from their byte-length/hash fingerprints, rejects every HEAD/index change and every working-path change outside allowed prefixes, rejects new allowed-path whitespace-diagnostic fingerprints, atomically transitions to `state=verified`, and emits `SCOPED CONTEXT EDIT VERIFIED`.
- `cancel` transitions an authenticated active receipt to `state=cancelled`; after any rejected `apply_patch`, the operator must cancel and rerun the same `prepare` command. The read-only guard cannot prove the writer or invocation count, so exactly one small `apply_patch` remains a registered operational constraint.
- `self-check` will call the same command functions in a temporary Git repository, require the protections to fail and pass at the expected points, exit nonzero on any assertion failure, and emit exactly `SCOPED CONTEXT EDIT OK` on success. Lifecycle same-path evidence relies on exit zero; the focused test and direct invocation separately assert the exact pass-signal text.
- Reason: this fixes the mechanical edit boundary while preserving `apply_patch` as the sole semantic writer.

### 2. Add focused contract tests

- File: `tests/test_context_edit_guard.py`
- Cover a successful prepare/check/apply/verify flow.
- Cover missing and duplicate anchors, absolute/path-traversal escapes, receipt tampering, target drift before the patch, explicit cancellation/re-preparation, required/forbidden assertion failures, outside-scope new and modified files, index-only changes, changes to an already-dirty outside file, and preservation of an unchanged dirty baseline.
- Cover pre-existing allowed-path whitespace diagnostics remaining accepted, newly introduced whitespace diagnostics being rejected, and terminal receipts being non-reusable without a fresh prepare.
- Cover the stable `self-check` pass signal.
- Reason: the sequence is reusable only if it fails closed on the exact failure modes that caused the repeated manual rework.

### 3. Validate the implementation locally

- Run `scripts/run_pytest.sh tests/test_context_edit_guard.py`.
- Run `python3 scripts/context_edit_guard.py self-check` and require `SCOPED CONTEXT EDIT OK`.
- Run `git diff --check -- scripts/context_edit_guard.py tests/test_context_edit_guard.py Tasks/scoped-context-edit`.
- Reason: prove both the Python contract and the executable registered entry point before lifecycle qualification.

### 4. Bootstrap a complete governed discovery candidate

- Write this exact request to `/private/tmp/scoped-context-edit-bootstrap-spec.json` and run `python3 scripts/discovery_bootstrap.py start --spec /private/tmp/scoped-context-edit-bootstrap-spec.json`:

```json
{
  "schema_version": 1,
  "task_id": "scoped-context-edit-bootstrap",
  "operation_kind": "other",
  "date": "2026-07-16",
  "sequence_name": "Scoped Context Edit",
  "outcome": "Apply one exact-context repository edit with currentness, scope, and postcondition evidence.",
  "why_repeatable": "Repository semantic edits recur and repeated manual anchor and verification mechanics have caused avoidable failures.",
  "steps": [
    {
      "step": "prepare",
      "command": "python3 scripts/context_edit_guard.py prepare --repo-root <repo-root> --target <target> --anchor <literal-anchor> --anchor-count 1 --receipt <receipt-path> --allow <allowed-path> --require-after <required-literal> --forbid-after <forbidden-literal>",
      "result": "prepared",
      "note": "Use only non-secret literals and keep the receipt outside the repository."
    },
    {
      "step": "check-current",
      "command": "python3 scripts/context_edit_guard.py check --receipt <receipt-path>",
      "result": "current",
      "note": "Run immediately before the semantic edit."
    },
    {
      "step": "apply-one-patch",
      "command": "apply_patch <one-small-patch>",
      "result": "applied",
      "note": "Use one bounded semantic patch; if rejected, run cancel and prepare again."
    },
    {
      "step": "verify-edit",
      "command": "python3 scripts/context_edit_guard.py verify --receipt <receipt-path>",
      "result": "verified",
      "note": "Reject stale, out-of-scope, postcondition, or new whitespace defects."
    },
    {
      "step": "cancel-rejected",
      "command": "python3 scripts/context_edit_guard.py cancel --receipt <receipt-path>",
      "result": "cancelled",
      "note": "Required after a rejected patch before re-preparing."
    },
    {
      "step": "verify-automation",
      "command": "python3 scripts/context_edit_guard.py self-check",
      "result": "passed",
      "note": "Exact same-path automation used for qualification and registered verification."
    }
  ],
  "inputs": [
    "A Git repository and one repository-relative regular target file.",
    "One non-secret literal anchor with its exact expected count.",
    "Repository-relative allowed paths and non-secret required or forbidden postconditions.",
    "An absolute receipt path outside the target repository."
  ],
  "failure_handling": "Stop on the first non-zero guard result; after a rejected apply_patch cancel and prepare a fresh receipt; lifecycle blockers use the canonical correction successor path.",
  "verified_path": "The exact self-check calls the same guard functions, exits nonzero on any failed assertion, and prints SCOPED CONTEXT EDIT OK only on success.",
  "dependencies": [
    {
      "kind": "file",
      "repository_key": "memory-knowledge",
      "path_or_sequence_id": "scripts/context_edit_guard.py"
    },
    {
      "kind": "file",
      "repository_key": "memory-knowledge",
      "path_or_sequence_id": "tests/test_context_edit_guard.py"
    }
  ]
}
```

- Treat the returned identities distinctly: `task_id=scoped-context-edit-bootstrap` owns bootstrap receipts and its started run; `sequence_name=Scoped Context Edit` determines the discovery filename slug; the generated manifest supplies the discovery/lineage id; lifecycle `--sequence-id scoped-context-edit` supplies the promoted registry id.
- `python3 scripts/context_edit_guard.py self-check` is the exact `verify-automation` command and `SCOPED CONTEXT EDIT OK` is the declared pass signal.
- Reason: the candidate must enter through the same canonical capture path future discoveries use; no hand-authored registered row or folder is allowed.

### 5. Drive canonical qualification, promotion, and registered verification

- Use the bootstrap response's `discovery_path` and `run_id` to complete its already-started run through the exact same path:
  1. `python3 scripts/sequence_guard.py guard --step verify-automation --command 'python3 scripts/context_edit_guard.py self-check' --source discovery_log --source-ref <discovery-path> --task-id scoped-context-edit-bootstrap --root /Users/kamenkamenov/memory-knowledge`
  2. `python3 scripts/context_edit_guard.py self-check`
  3. `python3 scripts/work_memory.py verify --run-id <bootstrap-run-id> --outcome passed --quality same-path --evidence 'Executed the exact guard-authorized scoped-context-edit self-check successfully.'`
  4. `python3 scripts/work_memory.py run-close --run-id <bootstrap-run-id> --result passed`
- Confirm that closed bootstrap run is qualification one for the current discovery bundle, then invoke:
  `python3 scripts/discovery_promotion_lifecycle.py drive --file <discovery-path> --sequence-id scoped-context-edit --use-when 'Guard a repository semantic edit that must use one exact anchor, one small apply_patch, stale-context rejection, and scoped post-edit verification.' --operation-kind other --automation-display 'memory-knowledge:scripts/context_edit_guard.py self-check' --pass-signal 'SCOPED CONTEXT EDIT OK'`
- Let the controller obtain the one remaining current-bundle qualification, atomically promote it, and run the registered bundle through the same guarded self-check. Require its returned stage to be `complete`.
- If the controller catalogs a blocker, use only its recorded correction/successor path; do not improvise a parallel promotion.
- Reason: this proves the sequence satisfies the existing readiness and promotion criteria rather than merely looking promotable.

### 5a. Correct the confirmed bootstrap-readiness lifecycle defect

- Files: `scripts/discovery_promotion_lifecycle.py` and `tests/test_discovery_promotion_lifecycle.py`.
- Before qualification, declare every existing readiness item through `sequence_discovery_log.py set-readiness` only when the candidate carries governed bootstrap provenance and its unmet predicates contain no structural gap other than `readiness` and optional `two-same-path-successes`.
- Keep readiness manual for hand-authored candidates and for candidates with any other structural gap.
- After readiness changes the bundle, collect fresh same-path qualifications for that current bundle before promotion.
- Correct and verify the failed registered `discovery-promotion-lifecycle` run through its canonical blocker-successor path, then resume the `scoped-context-edit` drive.
- Reason: the controller previously burned successful qualifications against an undeclared bootstrap readiness state until the run limit, making an otherwise complete governed candidate impossible to promote.

### 6. Verify discoverability and accumulated scope

- Confirm semantic discoverability by finding the unique registry row whose `use_when` describes exact-anchor, one-small-`apply_patch`, stale-context, and scoped-verification use. Do not claim generic selection by `operation_kind=other`; that selector is intentionally ambiguous when several `other` sequences exist.
- Prove executable selection explicitly:
  1. `python3 scripts/work_memory.py classify --task-id scoped-context-edit-registered-selection --operation-kind other --repeatable yes --meaningful-steps 5`
  2. `python3 scripts/work_memory.py select --task-id scoped-context-edit-registered-selection --sequence-id scoped-context-edit`
  3. Require the selection receipt to report `mode=registered`, `subject_id=scoped-context-edit`, and the promoted bundle/lineage identities.
- Confirm the registry row, promoted `sequence.md`, `dependencies.json`, lineage metadata, and registered passing event agree on the same bundle.
- Run focused tests again and review every changed in-scope file against this plan.
- Reason: the omission is closed only when the next agent can discover and use the sequence without reconstructing its commands.

## Files Allowed To Change

- `Tasks/scoped-context-edit/**`
- `scripts/context_edit_guard.py`
- `tests/test_context_edit_guard.py`
- `scripts/discovery_promotion_lifecycle.py`
- `tests/test_discovery_promotion_lifecycle.py`
- lifecycle-generated files under `operations/sequences/**`
- lifecycle-generated records in `operations/work-memory/events.jsonl`
- lifecycle-generated blocker view `operations/blockers/BLOCKERS.md`

## Verification Gates

1. Plan verification: independent verifier and critic find no actionable ambiguity, missing requirement, or invalid interface reference.
2. Implementation verification: focused tests and the executable self-check pass.
3. Promotion verification: lifecycle reports `complete` after two current-bundle discovery qualifications and one registered same-path pass.
4. Review verification: accumulated in-scope surface has no correctness, safety, scope, or plan-coverage finding.

## Stop Conditions

- Stop before adding any new repository or path outside the allowed set.
- Stop before changing any existing work-memory, discovery, promotion, or registry contract beyond the approved bootstrap-readiness lifecycle correction in step 5a.
- Stop rather than bypassing a lifecycle blocker or weakening a fail-closed check.
- Do not commit or push without separate explicit authorization.
