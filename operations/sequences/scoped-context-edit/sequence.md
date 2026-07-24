# scoped-context-edit

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

Guard a repository semantic edit that must use one exact anchor, one small apply_patch, stale-context rejection, and scoped post-edit verification.

## Outcome

Apply one exact-context repository edit with currentness, scope, and postcondition evidence.

## Required Inputs

- A Git repository and one repository-relative regular target file.
- One non-secret literal anchor with its exact expected count.
- Repository-relative allowed paths and non-secret required or forbidden postconditions.
- An absolute receipt path outside the target repository.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| prepare | python3 scripts/context_edit_guard.py prepare --repo-root <repo-root> --target <target> --anchor <literal-anchor> --anchor-count 1 --receipt <receipt-path> --allow <allowed-path> --require-after <required-literal> --forbid-after <forbidden-literal> | prepared | Use only non-secret literals and keep the receipt outside the repository. |
| check-current | python3 scripts/context_edit_guard.py check --receipt <receipt-path> | current | Run immediately before the semantic edit. |
| apply-one-patch | apply_patch <one-small-patch> | applied | Use one bounded semantic patch; if rejected, run cancel and prepare again. |
| verify-edit | python3 scripts/context_edit_guard.py verify --receipt <receipt-path> | verified | Reject stale, out-of-scope, postcondition, or new whitespace defects. |
| cancel-rejected | python3 scripts/context_edit_guard.py cancel --receipt <receipt-path> | cancelled | Required after a rejected patch before re-preparing. |
| verify-automation | python3 scripts/context_edit_guard.py self-check | passed | Exact same-path automation used for qualification and registered verification. |

## Failure Handling

Stop on the first non-zero guard result; after a rejected apply_patch cancel and prepare a fresh receipt; lifecycle blockers use the canonical correction successor path.

## Verification

- The exact self-check calls the same guard functions, exits nonzero on any failed assertion, and prints SCOPED CONTEXT EDIT OK only on success.

Pass signal: SCOPED CONTEXT EDIT OK

Promoted from `2026-07-16-scoped-context-edit`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
