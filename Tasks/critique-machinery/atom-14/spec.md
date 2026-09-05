# Atom 14 — a prose-waiver receipt proves an operator answered

Owner: Kamen Kamenov, 2026-09-05. Revised by Kamen after rejecting terminal interaction.

## Frozen defect

The current `prose-waiver-interview` accepts `waive` from a non-interactive model-controlled shell
and records `by: Kamen Kamenov` as a constant. Claude's inspection and Codex's independent replay
both produced an accepted receipt without evidence that Kamen answered.

## Approved atomic outcome

Either installed model client may launch the interview, but neither standard input nor command-line
arguments can supply its decision. One code-owned native macOS window displays the unchanged
`waive` and `decline` meanings. The operator clicks a choice and confirms macOS device-owner
authentication with Touch ID or the login password. No terminal interaction or setup command is
part of normal use.

The helper records the observed OS login/uid, approval mechanism, initiating projection and model
harness markers, helper identity, parent process, and wall-clock time. It binds those observations,
the exact request, fields, repository, meanings, adopted statement, and choice to a protected
Keychain proof. A model can launch the helper and can ask it to verify an existing proof, but cannot
pass a choice to it, satisfy device-owner authentication, read its secret silently, or mint a
receipt. Either installed projection verifies the same receipt without another operator ceremony.

## Practical value

The machinery model cannot approve its own prose exception or make Kamen appear to have approved a
choice he did not make. Kamen interacts only with the explanatory decision window and the normal
macOS authentication surface. Codex and Claude use one canonical security boundary.

## Stopping condition

The native helper refuses a choice supplied by a model argument before opening UI; Kamen's real GUI
choice and macOS authentication produce an operator-attributed `waive` receipt; `start` accepts it;
both installed projections verify it; an untrusted shell cannot silently read the protected value;
cross-request, missing-proof, invalid-proof, and historical receipt shapes refuse; existing complete
runs remain readable; both managed installs match generated projections; focused regression and
operator-path validation pass.

## Frozen real cases

- Claude model shell: the exploit recorded in `frozen-real/claude-inspection.md`.
- Codex model shell: the measured environment and accepted exploit in `prototype-0/`.
- Operator decision: the real proof-order request and Kamen's native `waive` plus macOS
  authentication.
- Cross-request reuse: the proof-order receipt presented for the real countable-KPIs request.
- Missing or invalid presence: the two committed 2026-09-04 receipts and a changed proof.
- Cross-client verification: the same real receipt checked by the Codex and Claude projected helper.

## Competing approaches and deciding evidence

1. **Terminal plus Keychain.** TTY and harness-marker gates stop model shells, but make Kamen run a
   command and type the decision. Kamen rejected that operator experience.
2. **Native window plus direct protected key.** The window works, but both Secure Enclave and
   software signing-key persistence fail on this Mac with `-34018`, the confirmed missing-entitlement
   boundary.
3. **Native window plus helper-restricted Keychain proof.** The helper owns the choice, device-owner
   authentication proves presence, one managed random value is readable only by byte-identical
   installed helpers, and verification is silent. The real prototype issued a proof, both
   client-shaped helpers verified it, a changed proof failed, and an untrusted shell remained blocked.

The deciding experiment ranks no terminal use, model inability to supply a choice, authenticated
operator success, silent cross-client verification, unforgeability, cross-request binding,
actionable refusals, backward readability, and frozen-input integrity in that order. Promotion
remains separate from the experiment.

## Boundary

Canonical edits are limited to Atom Building Machinery's `SKILL.md`, `atom_controller.py`, the
native helper source and universal executable, its tests, and the generated client projection
registry. Atom evidence and the BUILD-LEDGER record the protocol. Both managed installations are
refreshed through the existing installer. There is no commit and no `united-partners` edit. The
helper creates only its random protected value after a successful authenticated decision; no secret
is typed, printed, passed as an argument, or stored in a receipt.
