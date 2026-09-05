# Inspection — machinery upgrades A–C (Codex handover of 2026-09-05)

Inspected: memory-knowledge main at `a6282c31e9d59c04cc1a087d136a8a9c52c00c57` in the worktree
`/Users/kamenkamenov/.codex/worktrees/critique-machinery-publish-20260903` (HEAD == origin/main,
zero dirty tracked files, no AI attribution in the three commit messages). Every claim below was
replayed from committed bytes by Claude on 2026-09-05 with zero model calls. Replay copies lived in
the session scratchpad; no united-partners run, page or state was modified.

Verdict per atom: **A pass · B pass (two notes) · C pass on mechanism, one finding for Kamen's
decision (F1), two evidence findings (F2, F3), one boundary note (F4).**

## Atom A — commit `04a84f869f07ada58cb42c0aeeb6028a03e879f1` — PASS

| claim | replay | result |
| --- | --- | --- |
| five captured-case hashes | sha256 of each `source_ref` | 5 of 5 match |
| frozen matrix `82c6372a…`, sources `923e8914…`, state `0cd36c22…` | rehashed after replay | unchanged |
| live run `runs/claude-seat-s12-btm-page-v3` untouched | `diff -rq` vs frozen copy | identical (only `.gitattributes` added in the frozen copy) |
| assembly `d3cba1d6…`, proof event `a1f3c123…` | controller `status` on `atom-11/controller` | stage complete, 4 events, latest event matches |
| exact 23-char line `Always-on after launch.` records | `record_cell_readers` on a copy of cell `u-018-55cd0f78::upstream-trace` | outcome `agreement-defect`, quote recorded verbatim |
| one-character alteration goes to the owner | same with `launch!` | outcome `claim-without-grounded-words`, status unresolved, raw claim retained, first `ask-owner` question names the cell, `document` exit 2 naming the open question |
| `open --from-run --deliverable tactical_roadmap` | on the frozen state | six sources; id, key and value hash equal to the frozen registry |
| `rule-bulk` atomic | frozen assessment on a reset copy | filed 16; choices and cell ids equal to the hand-filed rulings; marker ` — reasoning drafted by Claude, adopted by the owner: `; queue empty after |
| `rule-bulk` refusal writes nothing | row 1 renumbered 99 | exit 2 naming the row set; matrix hash unchanged; no rulings file |
| `located --only disputed` | reset copy | byte-equal to the hand digest from its line 4; 20 blocks |
| one shared rule for instruction and refusal | `TRACE_GROUNDING_RULE` used at the reader instruction and the intake refusal; predicate `source_quote_is_grounded` | confirmed |
| installed projections | tree hash of `~/.claude` and `~/.codex` copies | equal to the registry at HEAD and to the ledger (`000d2abd…`, `4cfa10ed…`); `project_client_skills.py check` parity PASS for both clients |

The replay ran twice: once against the canonical script at HEAD, once against the installed
Claude projection. Both produced the same results line for line.

## Atom B — commit `391e28793017733cc94e4bb3a1f70f075ac1cd58` — PASS

Replayed with the controller extracted from the commit's own tree (`git archive 391e287…`),
from `/Users/kamenkamenov/united-partners`, superseding the committed replay copy of the real
attempt-1 run:

| claim | result |
| --- | --- |
| successor carries the earliest baseline | `inputs/change-baseline.json` = `c1ef6331…` (attempt 1) |
| `status` shows the ordered chain | `['atom-s12-approve-door-attempt-1', 'succ']`, closed false |
| accumulated surface | exactly `src/up_harness/tactical_roadmap.py`, the recorded unit-test bytecode path, `tests/unit/test_tactical_roadmap.py` |
| refusal: different atomic_step_id | `previous run atomic_step_id is 's12-approve-door'; require 's12-loop-advocates-named'` |
| refusal: completed predecessor | `… final/controller-run is complete and cannot be superseded` |
| refusal: tampered chain baseline | names the observed and required SHA-256 |
| refusal: changed allowed_paths | `new request allowed_paths differ from the earliest superseded baseline` |
| refused starts create no run directory | 0 of 4 created |
| second hop carries the same baseline; `authorize-next` refuses an incomplete chain | confirmed |
| self-hosted chain `controller → v2 → v3` | all three baselines `a5b4e0c4…`; v3 complete, 5 events, latest `c2d485b3…`, chain closed |
| idempotent `authorize-next` | re-run on the committed v3: same proof event, ledger hash unchanged, worktree still clean |
| three captured-case hashes; frozen attempt-3 surface `8ec63111…` with empty paths | match |
| source runs in united-partners | all four `atom-s12-approve-door*` controller runs byte-identical to the frozen copies |
| projection hashes | registry at `391e287…` equals the ledger (`4b1dd23f…`, `e4729274…`) |

Notes, not defects:

- **B-N1.** The frozen attempt-1 and attempt-3 copies refuse at `load-run` because their ledgers
  hold absolute experiment paths that now resolve to a different run (the un-suffixed
  `atom-s12-approve-door` directory, after our rename-to-attempt-N practice). That is a named
  refusal, not a crash. Codex replayed attempt 1 through a relocated copy whose only changed field
  is that path, with the event chain recomputed and the change receipted in
  `atom-12/experiment/replay-source/relocation-receipt.json`; the evidence hash is unchanged.
- **B-N2.** At HEAD, `start --supersedes` on a legacy predecessor refuses until the new request
  declares `contract_surface` (atom C's gate). With `{"kind": "render"}` added, the supersession
  starts and carries `c1ef6331…`. So the live rebuild path for our round-3 atoms works once the
  spec builders in `Tasks/step6-feedback-closure/final-benchmark-v2/make_spec.py` emit the
  declaration (Claude-owed).

## Atom C — commit `a6282c31e9d59c04cc1a087d136a8a9c52c00c57` — PASS on mechanism, findings below

Replayed with the HEAD controller from `/Users/kamenkamenov/united-partners` on the committed
`declared-real` requests:

| request | result |
| --- | --- |
| `named-assigner` (pinned-string from `DOOR_FORM`) | starts; status carries the declaration |
| `card-inside-phase` (integer + enum from `ROADMAP_PHASES`) | starts |
| `generic-line-retired` (`kind: render`) | starts |
| `proof-order` (prose) | exit 2, no directory; names the field, the three misread runs, the two next actions |
| `countable-kpis` (prose) | exit 2, same refusal shape |
| `named-assigner-misspelled` | exit 2: `field 'ownership[].owenr' does not resolve at 'owenr'; available keys are ['budget_frame', 'cadence', 'dependencies', 'element', 'owner']` |
| hand-written `prose_waiver` block in the request | refused: `remove it, run prose-waiver-interview` |
| interview answer `waive` | receipt binds request hash `4a257984…` (identical to Kamen's committed receipt for the same request), field, repository, both displayed meanings, the adopted statement, date; `start --prose-waiver-interview` then starts and `status` shows the statement |
| interview answer `decline` | interview `declined`; start refused: `Kamen Kamenov chose 'decline' … remains blocked until it uses a structured field` |
| interview answer `yes` | refused: `choose one word: 'waive' or 'decline'` |
| proof-order's interview passed to countable-kpis | refused: `bound to a different request or repository` |
| record-experiment contract scan on the real named-assigner assembly | real declaration: green, `owner` observed in `scripts/atom_check.py`; a declared leaf the module never reads: refused with the missing field and the observed keys |
| self-hosted chain `controller-final-bootstrap → controller-self-hosted-2` | complete, 5 events, latest `f7bc7a9e…`, chain closed; experiment event stores `contract_scan` (`python-ast-string-key-scan`); promotion receipt carries the contract surface; surface `1b1210eb…` = the four canonical paths |
| operator order | committed evidence returns 0, 2, 0; reproduced directly on the start gate at HEAD |
| installed projections | equal to the registry at HEAD and to the ledger (`c18b7c64…`, `87387081…`); parity PASS |

### F1 — the interview proves the word, not who typed it (needs Kamen's decision)

`prose-waiver-interview` reads the answer from standard input and writes `by: "Kamen Kamenov"`
unconditionally (`atom_controller.py` lines 1183 and 1299). Claude typed `waive` through a pipe
and received a receipt of the same form as the two committed final receipts
(`atom-13/waiver-interviews/proof-order-final-waive`, `countable-kpis-final`, dated 2026-09-04).
The ledger calls those "Kamen's final `waive` choices". Nothing in the committed bytes shows
whether Kamen or Codex typed them, and no message from Kamen in this session records such a
choice. The claim "a model-written waiver is not accepted" therefore holds for the JSON block
only; a model can still answer the interview.

Recommended fix (one atom, Codex): refuse a non-terminal standard input, record the terminal
identity and session in the receipt, and require the operator's own words after the choice word
so the receipt carries something a model would not be invited to write. Until then, treat the two
2026-09-04 receipts as unverified unless Kamen confirms he made those choices.

### F2 — operator-order evidence was produced on the accepted assembly, not the promoted bytes

`operator-order-final/relocated/operator-evidence/summary.json` records controller SHA-256
`2b8269f8…`; the promoted controller at HEAD is `d209324a…`. The two differ by an eleven-line
rewrite of `REQUEST_FIELDS` (same set). The 0, 2, 0 outcome reproduces at HEAD on the start gate
directly, so the claim stands; the receipt should have been regenerated after promotion.

### F3 — the contract-scan refusal has no committed red

No test and no committed evidence shows `record-experiment` refusing when a champion module
does not read the declared leaf (`grep "static scan did not see"` over `tests/` and the atom-13
evidence returns nothing outside the controller source). Claude fired it on the real
named-assigner assembly (table above), so the code path works; the suite should carry that case.

### F4 — boundary note: a united-partners file was edited

`Tasks/step6-feedback-closure/build_atom.py` in united-partners is modified and uncommitted
(+20 / −4): `ATOM_CONTROLLER` environment override, `contract_surface` passthrough from the spec,
refusal of a spec-supplied `prose_waiver`, and `--prose-waiver-interview` passthrough. Claude's
handover (`CODEX-HANDOVER-ATOM-C-STRUCTURED-FIELDS.md` line 89) asked for the round-3 order to be
run "end to end through `build_atom.py` under the new controller", which implies this edit, but
it sits outside the memory-knowledge scope and is committed only on Kamen's order.

## Test evidence

- Focused suites at HEAD (`test_critique_machinery`, `test_atom_building_machinery`,
  `test_client_skill_projections`, `test_install_skills`): 85 passed, 0 failed (26 s).
- Full suite at HEAD under Claude's sandbox: 2,258 passed, 13 failed, 1 skipped. Two failures
  were caused by a bytecode cache Claude's own replays wrote under
  `skills/atom-building-machinery/scripts/`; after removing it both pass (21 passed). One is the
  pre-existing prevention-contract byte-stability assertion Codex disclosed. The remaining ten
  (`test_info_intake_machinery` ×7, `test_screenshot_source_locator` ×3) reference the
  `/usr/bin/codex` runner and touch none of the eight canonical files the three commits changed;
  Codex's receipt reports them passing unrestricted, which Claude could not reproduce in the
  sandbox and does not vouch for.

## Files this inspection touched

- Created: `Tasks/critique-machinery/S12-MACHINERY-UPGRADE-A-C-INSPECTION.md` (this file).
- Removed in the worktree: the ignored `skills/atom-building-machinery/scripts/__pycache__/`
  directory Claude's replays created. Worktree tracked files remain clean.
