# Sequence Discovery Log: Scoped Context Edit
ReadyAtUtc: 2026-07-16T09:43:16Z

DiscoveryId: discovery-1c6cdb98-3710-5220-895a-11ae9a2822c8
Status: promoted
PromotedSequenceId: scoped-context-edit
CreatedAtUtc: 2026-07-16T07:03:10Z
BootstrapRequestSha256: 0094b3b6feaefda39fd76075c11a7cb1e5ef1d1ec1bdf6b3a9238f5ea8c486dd
RegisteredSequenceMatch: none

## Intended Outcome

Apply one exact-context repository edit with currentness, scope, and postcondition evidence.

## Why This Looks Repeatable

Repository semantic edits recur and repeated manual anchor and verification mechanics have caused avoidable failures.

## Required Inputs, Auth, Or Environment

- A Git repository and one repository-relative regular target file.
- One non-secret literal anchor with its exact expected count.
- Repository-relative allowed paths and non-secret required or forbidden postconditions.
- An absolute receipt path outside the target repository.

## Commands And Observations

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

## Verified Path

- The exact self-check calls the same guard functions, exits nonzero on any failed assertion, and prints SCOPED CONTEXT EDIT OK only on success.

## Promotion Readiness

- [x] Commands are stable enough to script or document.
- [x] Required inputs are known.
- [x] Failure handling is known.
- [x] Verification evidence is known.
- [x] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
