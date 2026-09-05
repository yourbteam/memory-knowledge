# Inspection — Correction Atom 3 / Atom 14 (commit `1684116126c486cd5bac14359584fbf3f8928dff`)

Inspected 2026-09-05 by Claude from committed bytes in
`/Users/kamenkamenov/.codex/worktrees/critique-machinery-publish-20260903`. `origin/main` and
`HEAD` both resolve to `1684116…`, parent `a6282c3…`, message "Require authenticated operator
presence for prose waivers", no AI attribution, 106 files (7 operative + 99 under `atom-14/`).
Zero model calls were spent. No native window and no authentication prompt was opened; every
live probe used argument, verification, or start paths that refuse before UI.

**Verdict: REVISE.** The mechanism is sound where it was claimed; two findings need a further
atom before the waiver can be trusted on the runs it was built for (F1, F2). Four notes follow.

## What reproduces from committed bytes

| claim | replay | result |
| --- | --- | --- |
| helper is a signed universal Mach-O | `file`, `lipo -archs`, `codesign --verify --strict` | x86_64 + arm64; ad-hoc signature valid, satisfies its designated requirement |
| canonical and installed helpers share `5fa86bda…` | sha256 of canonical, `~/.claude`, `~/.codex` copies | all three equal |
| installed projections `0c1d77bb…` (Codex), `13ec6141…` (Claude) | tree hash of both installs vs registry at HEAD vs ledger | equal; `project_client_skills.py check` parity PASS for both clients; policies retain `codex exec` / `claude -p` |
| helper refuses an argument-supplied choice before UI | `prose_waiver_approval authorize waive` on the installed Claude helper | exit 2, `the decision cannot be supplied by arguments; choose only in the native window` |
| helper refuses to run from a non-installed path | canonical worktree copy, `verify 0 0` | exit 2 naming the path and the installer |
| real operator receipt verifies; a changed digest refuses | installed helper `verify` on the committed `native-interview` receipt, then one hex digit flipped | `verified`; then `receipt proof does not match the protected approval key` |
| signed payload is request-bound | decoded the committed signed payload | request `4a257984…`, repository `/Users/kamenkamenov/united-partners`, field `proof_building_order`, choice `waive`; the controller compares request hash, repository root, fields, code-owned meanings, adopted statement and date before accepting |
| both legacy Atom 13 receipts refuse a new start | HEAD `start --prose-waiver-interview` with each 2026-09-04 interview | refused: missing `operator`, `presence_proof`, unexpected `by` |
| cross-request reuse refuses | committed native receipt against the countable-KPIs request | `bound to a different request or repository` |
| forged receipt refuses | committed `forged-interview`; and my own digest flip inside a copied interview | `receipt proof does not match…`; `receipt differs from the code-recorded operator interview` |
| the real receipt starts its own request | HEAD `start` with the committed native interview on the proof-order request | starts; status shows operator `kamenkamenov`, projection `codex`, the adopted statement |
| historical completed runs remain readable | HEAD `status` on `atom-13/controller-self-hosted-2` and `atom-11/controller` | complete, readable |
| installed controller no longer dies at import | installed Claude controller: `status` on a memory-knowledge run, `start` of the real named-assigner request from united-partners | both succeed |
| experiment 6/6 at assembly `c4fec1a3…`, promotion `e4b9ce87…`, proof `eaac5e4a…`, surface `d1470303…` | `status` on `controller-gui-runtime`, sha256 of the surface file | all match; `controller-gui-bootstrap` promoted the six-file surface including SKILL.md, the Swift source and the binary |
| focused verification | `run_pytest.sh` on the controller, projection and installer suites at HEAD | 63 passed, 0 failed |

## Findings

### F1 — the window binds to whatever request the launcher chose, and does not say which (revise)

The helper's window shows only the field names and the repository root
(`prose_waiver_approval.swift` line 238); the authentication prompt shows only the word
`waive` or `decline` (line 204). Neither shows the atom id or the request hash. The controller
builds the context (`_authorization_context`) from the request it was given, but any model can
run the installed helper directly with a context it wrote for any request whose hash it computed,
and a model can also hand-write an interview directory around a genuine authorization, because
`start` checks only that the signed payload matches the request it is started with.

Consequence: if Kamen is told "approve the KPI atom" while the window was launched for a
different request declaring the same field name, his click and authentication produce a valid
receipt for the request he did not intend. That is the exact shape the atom exists to prevent
("cannot make Kamen appear to have approved a choice he did not make"). The recorded cases
(`operator-validation/cases/*shell-self-approval.json`) cover only the argument-supplied choice.

Fix in one atom: pass `atomic_step_id` and the request hash in the authorization context, sign
them into the payload, display both in the window text and in the authentication reason, and
have `start` compare them. The receipt Kamen produced on 2026-09-05 stays valid for its request.

### F2 — the installed controller still cannot finish a united-partners atom (revise)

The deferred import resolves blocker support from the canonical module root or the run's recorded
repository root (`atom_controller.py` lines 927–953). From the installed Claude controller,
`authorize-next` on the completed real run
`Tasks/step6-feedback-closure/runs/atom-s12-approve-door/controller-run` refuses:

```
canonical blocker support is unavailable; require blocker_catalog.py and work_memory.py
together in one of ['/Users/kamenkamenov/.claude/scripts', '/Users/kamenkamenov/united-partners/scripts']
```

`record-validation` calls the same function (line 2554). So `status` and `start` now work from
the installed skill, but the two stages that close an atom do not, for every run whose repository
is united-partners, which is all of ours. The same command from the canonical checkout succeeds.
The ledger's claim ("each installed controller also started the exact request into its own real
run") is true as written; the blocker `blk-01c986…` is closed for startup only, and the standing
CM-D2 item remains open for validation and authorization. `build_atom.py` in united-partners still
points `ATOM_CONTROLLER` at the published checkout for this reason.

### N1 — key lifecycle is bound to the exact helper bytes

The Keychain item's access list names the two installed helper paths through
`SecTrustedApplicationCreateFromPath` (lines 158–166) and the helper is ad-hoc signed. Any
rebuild of the helper changes its identity, so every previously issued receipt stops verifying
(the helper reads the key with `createIfMissing: false` at `verify`) and the first authorize after
a rebuild raises a Keychain "allow" prompt rather than creating a fresh key. Not exercised live;
read from the source and the signature flags. Worth stating in `SKILL.md` before the first
rebuild surprises an operator.

### N2 — an untrusted `security` read is stopped by a dialog, not by policy

The ledger's "untrusted read returned zero key bytes before the five-second guard" means the
macOS access prompt was left unanswered. A model-launched `security find-generic-password` shows
that prompt to Kamen; "Always Allow" would hand the key to every shell. The helper cannot prevent
this; the data-protection Keychain that would (`-34018`) needs an entitled app. Kamen should never
allow that item to anything but the two helpers.

### N3 — `parent_process_name` carries no information for shell launches

The real receipt records `parent_process_name: "unknown"` (`operator-validation/native-interview/
prose-waiver-receipt.json`), because `NSRunningApplication` resolves only GUI applications and the
launcher is a Python process. The ledger lists "parent process" among the observations the receipt
records; in practice it records the pid and the string `unknown`.

### N4 — blocker and work-memory records are outside the commit

`operations/blockers/BLOCKERS.md` and `operations/work-memory/events.jsonl` are modified and
uncommitted in the worktree; the ledger's "blocker `blk-01c986…` is recorded, same-path verified,
and closed" cannot be reproduced from `1684116…`. The handover declares this exclusion deliberate.

## Boundary check

No united-partners file was changed by the commit. Claude's own replays wrote only under the
session scratchpad; a bytecode cache created under the worktree's `skills/` by direct controller
invocations was removed again (ignored path, tracked tree clean apart from the two files in N4).

## Files this inspection touched

- Created: `Tasks/critique-machinery/S12-MACHINERY-ATOM-14-INSPECTION.md` (this file).
