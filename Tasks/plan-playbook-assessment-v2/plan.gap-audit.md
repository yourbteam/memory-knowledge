# Plan Playbook V2 Internal-Readiness Audit

Current converged plan revision: `1d770a88cac46583ad4a5e43f245b3e5eb2075888adb7316c2ad4e1cdc169ee8`

## Cycle 1 Assessment

### Boundary

This cycle assesses internal implementation readiness only: self-sufficiency, decision completeness, state and data flow, schemas, failures, resume/idempotency, validation, grounding, approval boundaries, contradictions, vague wording, and one-shot handoff. Requirements breadth and end-to-end runtime satisfaction remain owned by later gates.

The approved research package is terminal `PASS`; its payload hashes match `research-package/manifest.json`.

### Section Inventory

The plan has no pre-heading text and contains 49 deterministic heading units.

| unit | lines | section | role |
| --- | --- | --- | --- |
| U01 | 1-2 | Plan Playbook V2 Implementation Plan | title |
| U02 | 3-16 | Goal and Terminal Outcome | outcome contract |
| U03 | 17-18 | Scope | container |
| U04 | 19-29 | In scope | scope list |
| U05 | 30-37 | Out of scope | exclusions |
| U06 | 38-51 | Frozen Requirements | requirement table |
| U07 | 52-53 | Locked Architecture | container |
| U08 | 54-73 | Candidate-first development | architecture |
| U09 | 74-89 | Parent and agent ownership | ownership |
| U10 | 90-108 | Controller boundary | component boundary |
| U11 | 109-110 | Controller Contract | container |
| U12 | 111-138 | CLI | command and envelope contract |
| U13 | 139-163 | Frozen charter | schema |
| U14 | 164-186 | Evidence entry modes | evidence flow |
| U15 | 187-211 | Surface map and decisions | artifact schema |
| U16 | 212-254 | Findings, dispositions, and gate results | hardening schema |
| U17 | 255-265 | Profiles and shared budgets | policy/state |
| U18 | 266-312 | Plan package | package contract |
| U19 | 313-331 | Hardening order and invalidation | lifecycle |
| U20 | 332-333 | Skill Contract and References | container |
| U21 | 334-339 | Change 1: candidate operator contract | change |
| U22 | 340-351 | Change 2: reference contracts | change |
| U23 | 352-357 | Change 3: agent metadata | change |
| U24 | 358-359 | Consumer Integration | container |
| U25 | 360-367 | Change 4: task-workflow | integration |
| U26 | 368-384 | Change 5: convergence loop | integration |
| U27 | 385-386 | Practical Evaluator | container |
| U28 | 387-408 | Fixtures | evaluator inputs |
| U29 | 409-434 | Matrix | evaluator lifecycle |
| U30 | 435-458 | Evaluator exchange schemas | schemas |
| U31 | 459-488 | Exact planner and downstream outputs | schemas |
| U32 | 489-516 | Locked thresholds | acceptance |
| U33 | 517-518 | Tests | container |
| U34 | 519-546 | Change 6: controller and lifecycle tests | tests |
| U35 | 547-561 | Change 7: contract and consumer tests | tests |
| U36 | 562-577 | Change 8: evaluator tests | tests |
| U37 | 578-583 | Change 9: managed-skill and promotion tests | tests |
| U38 | 584-585 | Candidate Installation and Evaluation | container |
| U39 | 586-599 | Change 10: candidate managed installation | operation |
| U40 | 600-603 | Change 11: live blind matrix | evaluation |
| U41 | 604-605 | Transactional Promotion | container |
| U42 | 606-664 | Change 12: promotion controller | transaction |
| U43 | 665-676 | Requirement Acceptance Matrix | traceability |
| U44 | 677-703 | Validation Commands | validation |
| U45 | 704-716 | Failure, Resume, and Idempotency | recovery |
| U46 | 717-732 | Ordered Execution | sequence |
| U47 | 733-747 | Granular Approval Units | authorization |
| U48 | 748-766 | Closeout Checklist | closeout |
| U49 | 767-769 | One-Shot Readiness | readiness assertion |

### Coverage Matrix

`C` means all internal-readiness lenses passed. `G-nnn` names a blocker. Container units are covered by their children.

| unit | decision/data/schema/failure/test/grounding/scope/consistency/handoff result | evidence |
| --- | --- | --- |
| U01 | C | `plan.md:1` |
| U02 | G-005 | Plan/package-only outcome conflicts with evaluator evidence language at `plan.md:12,449`. |
| U03 | C via U04-U05 | `plan.md:17-37` |
| U04 | C | `plan.md:19-29` |
| U05 | C | `plan.md:30-36` |
| U06 | C | `plan.md:40-50` |
| U07 | C via U08-U10 | `plan.md:52-108` |
| U08 | C | `plan.md:54-72` |
| U09 | G-001, G-004 | Pre-spawn lifecycle and FILE transfer are incomplete at `plan.md:76-88`. |
| U10 | G-001 | State authority lacks an exact state/transition contract at `plan.md:92-107`. |
| U11 | C via U12-U19 | `plan.md:109-331` |
| U12 | G-001, G-002, G-003, G-004 | CLI validates attempts post-run and lacks complete aggregate/materialization commands at `plan.md:113-137`. |
| U13 | C | `plan.md:141-162` |
| U14 | G-007 | Kind-specific source validation is absent at `plan.md:166-185`. |
| U15 | C | `plan.md:189-210` |
| U16 | G-003, G-004 | Internal/shared schemas conflict and FILE bytes cannot cross the assessment boundary at `plan.md:214-253`. |
| U17 | C | `plan.md:257-264` |
| U18 | G-004, G-006 | Existing-root package transaction and exact manifest lifecycle are undecided at `plan.md:268-311`. |
| U19 | G-001, G-006 | Stage order is clear; command transitions and re-emission are incomplete at `plan.md:315-330`. |
| U20 | C via U21-U23 | `plan.md:332-357` |
| U21 | C | `plan.md:334-338` |
| U22 | C | `plan.md:342-350` |
| U23 | C | `plan.md:352-356` |
| U24 | C via U25-U26 | `plan.md:358-384` |
| U25 | C | `plan.md:360-366` |
| U26 | G-002, G-003 | Generic consumer uses task-specific IDs and incompatible failure envelopes at `plan.md:368-377`. |
| U27 | C via U28-U32 | `plan.md:385-516` |
| U28 | C | `plan.md:389-407` |
| U29 | G-005 | Matrix promises plan/package-only implementers at `plan.md:424-433`. |
| U30 | G-005 | `visible_evidence` lacks implementer nullability at `plan.md:437-457`. |
| U31 | C except G-005 dependency | `plan.md:461-487` |
| U32 | C | `plan.md:491-515` |
| U33 | C via U34-U37 | `plan.md:517-583` |
| U34 | G-001, G-003, G-004, G-006, G-007 | Controller tests cannot be exact until the missing contracts are locked at `plan.md:521-543`. |
| U35 | G-002, G-003, G-005 | Generic-ID, aggregate-failure, and isolation tests are missing at `plan.md:549-560`. |
| U36 | G-005 | Evaluator isolation test depends on unresolved visibility at `plan.md:564-576`. |
| U37 | C | `plan.md:580-582` |
| U38 | C via U39-U40 | `plan.md:584-603` |
| U39 | C | Installer syntax is grounded at `plan.md:588-598`. |
| U40 | G-005 | Live matrix inherits input isolation ambiguity at `plan.md:600-602`. |
| U41 | C via U42 | `plan.md:604-664` |
| U42 | C | `plan.md:608-663` |
| U43 | G-001 through G-007 | Acceptance cannot be proved while blockers remain at `plan.md:667-675`. |
| U44 | C | `plan.md:679-702` |
| U45 | G-001, G-006, G-007 | Atomicity/evidence assertions lack implementation protocols at `plan.md:706-715`. |
| U46 | G-001 through G-007 | Ordered sequence depends on unresolved contracts at `plan.md:719-731`. |
| U47 | C | `plan.md:735-746` |
| U48 | G-001 through G-007 | Checklist cannot be satisfied one-shot while blockers remain at `plan.md:750-765`. |
| U49 | G-001 through G-007 | The no-unresolved-choice assertion at `plan.md:769` is unsupported. |

### Blocker Gap Ledger

| gap_id | practical consequence | evidence | required correction | status |
| --- | --- | --- | --- | --- |
| GAP-001 | An agent can run before its envelope, slot, budget, and retry identity are controller-reserved; post-run rejection cannot undo the ungoverned attempt. | `plan.md:92-105,113-150,293-300`; `skills/_shared/agent_slot_ledger.py:16-17,98-176` | Add exact state schema and pre-spawn prepare/begin transition with attempt token, transition table, retries, timeout, replay, cap semantics, and live slot-ledger v2 evidence. | Closed by `plan.md:133-150,293-300`; pending fresh Cycle 2 assessment. |
| GAP-002 | Generic convergence tasks can receive this plan's R1-R7 IDs or lack outer stage/iteration/attempt identity, causing unknown-requirement rejection. | `plan.md:156-166,425-437`; `skills/_shared/convergence_state.py:441-459` | Make `stage-result` a generic adapter bound to active convergence state and arbitrary package requirement IDs. | Closed by `plan.md:156-166,425-437`; pending fresh Cycle 2 assessment. |
| GAP-003 | GAPS/BLOCKED plan results will be rejected because internal finding/blocker records do not match the live convergence-state nested schemas. | `plan.md:152-166`; `skills/_shared/convergence_state.py:461-501` | Keep internal records separate and define exact deterministic aggregate gap/blocker mappings for all four verdicts. | Closed by `plan.md:152-166`; pending fresh Cycle 2 assessment. |
| GAP-004 | Assessment-only agents cannot write FILE audits, while their permitted output has no field carrying the exact Markdown bytes for the parent to persist. | `plan.md:74-88,148-150,274-289`; `skills/doc-gap-closure-loop/SKILL.md:107-111` | Add raw artifact payload/hash transfer and a controller-validated parent materialization command with no-rewrite proof. | Closed by `plan.md:148-150,274-289`; pending fresh Cycle 2 assessment. |
| GAP-005 | Extra repository evidence can repair a weak plan during evaluator scoring, or forbidding it can make the task artificial; the plan currently says both. | `plan.md:508-513`; `analysis.md:154-171` | Lock implementer isolation. The selected outcome is plan/package plus answer-free output contract only; visible evidence and research package must be null for implementers. | Closed by `plan.md:508-513` and `analysis.md:162-171`; pending fresh Cycle 2 assessment. |
| GAP-006 | Initial emission or revision can leave a mixed package in an existing task root or destroy non-package siblings; exact manifest and crash recovery are absent. | `plan.md:302-351`; `research_package.py:1729-1739` | Define an existing-root owned-file transaction, exact manifest schema, journal, backup/tombstones, commit point, rollback, recovery, stale-file removal, and replay. | Closed by `plan.md:302-351`; pending fresh Cycle 2 assessment. |
| GAP-007 | DIRECT entry can trust a claimed command digest without captured bytes, argv, exit code, or containment proof, defeating evidence sufficiency. | `plan.md:193-219` | Accept only controller-read, root-contained LOCAL_FILE/SUPPLIED_INPUT records; route dynamic command/runtime evidence to research and forbid it from satisfying CURRENT_BEHAVIOR in DIRECT mode. | Closed by `plan.md:193-219`; pending fresh Cycle 2 assessment. |

### Cleanup List

| id | issue | disposition |
| --- | --- | --- |
| CLEAN-001 | V2-003 ledger text names an older surface-map predicate. | Update it to say the later Markdown-unit/tiny predicate superseded the earlier closure. |
| CLEAN-002 | Evaluator tests do not name their file. | Put them in `tests/test_plan_playbook_v2_evaluator.py`. |
| CLEAN-003 | Candidate install does not explicitly state changed installed/source equality. | State equality for candidate and research-playbook, not only unrelated-skill preservation. |
| CLEAN-004 | Focused pre-evaluation tests omit `tests/test_research_playbook_v2.py`. | Add it to the focused command. |

### Closure Proof for Prior Findings

The plan-verification ledger has all C01-C14 checked, all findings resolved, and iteration 6 PASS. This gate independently rechecked the resulting plan. Most prior closures remain valid. GAP-001 reopens the attempt lifecycle boundary; GAP-002/GAP-003 reopen convergence handoff; GAP-004 reopens FILE artifact ownership; GAP-005 reopens evaluator exchange isolation; GAP-006 reopens existing-root package ownership; GAP-007 narrows the remaining DIRECT evidence defect. All seven are inside approved R2, R4, R6, and R7 obligations.

### Readiness Result

`GAPS`: seven blockers require design invention before implementation can begin. `plan.md` is not internally ready on this revision.

## Cycle 1 Plan

### Gap-To-Fix Map

| gap | target | locked correction | validation |
| --- | --- | --- | --- |
| GAP-001 | Controller CLI/state | Pre-spawn attempt reservation and complete transition table. | Reject malformed/exhausted attempts before spawn; prove idempotent begin/finalize and retry accounting. |
| GAP-002 | Convergence integration | Generic aggregate adapter derives active IDs and outer stage identity. | Unrelated requirement IDs and repeated outer attempts record correctly; foreign IDs fail. |
| GAP-003 | Aggregate schema | Exact internal-to-convergence mapping for gaps/blockers. | PASS/GAPS/BLOCKED/CAP_REACHED round-trip through `convergence_state.py record-stage`. |
| GAP-004 | Artifact transfer | Agent returns exact Markdown bytes/hash; parent materializes controller-validated bytes. | Persisted bytes equal returned bytes; tamper/path/rewrite fail. |
| GAP-005 | Evaluator isolation | Implementers receive plan/package and answer-free output contract only. | Any visible evidence, research package, or hidden gold in implementer input fails. |
| GAP-006 | Package transaction | Existing-root owned-file transaction and exact manifest. | Failure injection restores prior owned files and preserves non-package siblings. |
| GAP-007 | DIRECT evidence | Kind-specific contained files; dynamic command/runtime evidence is rejected and routed to research rather than accepted through an ungrounded receipt. | Fake hash, symlink escape, unsupported kind, and command-output evidence fail before drafting. |

## Cycle 1 Edits

The assessment agent remained assessment-only. The parent then applied the complete seven-gap fix map to `plan.md` and reconciled it with the live helper contracts:

- GAP-001: added the exact controller state, pre-spawn attempt token, output binding, retry/cap behavior, and slot-ledger v2 transition/evidence rules.
- GAP-002/GAP-003: separated internal gate records from the generic aggregate adapter and bound its output to arbitrary active convergence requirements and all four live verdict schemas.
- GAP-004: added exact Markdown transfer bytes/hash and parent-only fixed-path materialization without reconstruction.
- GAP-005: locked evaluator implementers to plan/package plus answer-free output schema only.
- GAP-006: added the exact existing-root transaction, manifest, journal, commit point, rollback, recovery, and replay behavior.
- GAP-007: limited DIRECT evidence to controller-read contained files/inputs and routed command/runtime evidence to the research boundary.

Live reconciliation also removed the invalid `--artifact-id plan-package` consumer argument: `convergence_state.py record-stage` registers the PASS manifest directly from `artifact_paths` in the result file.

## Cycle 1 Validation

### Post-Edit New-Gap Pass

The parent rechecked every changed unit against the seven gap definitions, the frozen R1-R7 requirements, and both live helpers. All seven prior gaps have closure text on the edited revision and no scope expansion was introduced. This validation does not declare convergence; Cycle 2 must perform a fresh full-document no-edit assessment.

### Validation Evidence

- The assessed pre-edit revision had 769 plan lines, 207 analysis lines, and 489 ledger lines.
- All planning/research JSON artifacts parsed.
- All research-package payload hashes matched the manifest and its terminal verdict was PASS.
- Current assessed plan hash: `2da519c653efb3b22b2627020eccee9514d34952a898f8d527a936409d9c608a`.
- The flexible-word scan found no unresolved placeholder; blockers came from semantic contract tracing.
- Live consumer tracing confirmed conflicts at `plan.md:135,376` against `skills/_shared/convergence_state.py:441-480`.
- Post-edit source reconciliation confirmed slot states and evidence at `skills/_shared/agent_slot_ledger.py:16-17,98-176`, live convergence nested schemas and artifact registration at `skills/_shared/convergence_state.py:441-501`, and the corrected consumer command at `plan.md:425-437`.

### Final Readiness Proof

| category | status | reason |
| --- | --- | --- |
| Runtime entry/data flow | corrected; awaiting fresh assessment | GAP-001 and GAP-002 have closure text. |
| Schemas/interfaces/artifacts | corrected; awaiting fresh assessment | GAP-003 and GAP-004 have closure text. |
| Edge/failure behavior | corrected; awaiting fresh assessment | GAP-003 and GAP-006 have closure text. |
| Resume/idempotency | corrected; awaiting fresh assessment | GAP-001 and GAP-006 have closure text. |
| Validation/tests | corrected; awaiting fresh assessment | Exact tests now cover each corrected contract. |
| Repo grounding | corrected; awaiting fresh assessment | Live slot and convergence helpers were reconciled. |
| Approval and scope boundaries | ready | No wider repository/action authorization is introduced. |
| Internal consistency | corrected; awaiting fresh assessment | GAP-002, GAP-003, and GAP-005 have closure text. |
| One-shot handoff | not yet proven | The hard-stop rule requires a fresh no-edit Cycle 2 assessment. |

Cycle 1 terminal verdict remains `GAPS`; convergence is intentionally not claimed after edits.

## Cycle 2 Assessment

### Boundary

This was a fresh, no-edit, full-document internal-readiness assessment of
`plan.md` at SHA-256
`55fdf0a7c4d7cae5d0ecda16602b074189722cd7d773669912e82f57201ec414`.
It proves internal readiness only; requirements breadth and end-to-end
satisfaction remain owned by the next two gates.

The current plan contains 1,168 lines, no pre-heading text, and 49
fenced-code-aware deterministic ATX-heading units.

### Lens Key

`D` decision completeness; `R` runtime flow; `S` schema/API semantics; `F`
failure/resume/idempotency; `V` validation and acceptance; `G` repository
grounding; `A` approval and scope; `X` contradictions; `W` vague choices; `H`
implementation handoff. `C` means checked with no blocker. `NA` is used only
for titles or containers whose substantive children are checked explicitly.

### Deterministic Section Inventory

| unit_id | plan.md lines | section/title | relevance |
| --- | ---: | --- | --- |
| U01 | 1-2 | Plan Playbook V2 Implementation Plan | title |
| U02 | 3-16 | Goal and Terminal Outcome | terminal outcome |
| U03 | 17-18 | Scope | container |
| U04 | 19-31 | In scope | authorized surfaces |
| U05 | 32-40 | Out of scope | exclusions |
| U06 | 41-54 | Frozen Requirements | requirements |
| U07 | 55-56 | Locked Architecture | container |
| U08 | 57-79 | Candidate-first development | candidate topology |
| U09 | 80-103 | Parent and agent ownership | ownership and isolation |
| U10 | 104-124 | Controller boundary | authority |
| U11 | 125-126 | Controller Contract | container |
| U12 | 127-294 | CLI | commands, state, attempts, adapters |
| U13 | 295-320 | Frozen charter | charter and requirement schema |
| U14 | 321-354 | Evidence entry modes | evidence flow |
| U15 | 355-379 | Surface map and decisions | planning artifacts |
| U16 | 380-437 | Findings, dispositions, and gate results | hardening records |
| U17 | 438-450 | Profiles and shared budgets | profiles and caps |
| U18 | 451-524 | Plan package | package transaction |
| U19 | 525-544 | Hardening order and invalidation | gate lifecycle |
| U20 | 545-546 | Skill Contract and References | container |
| U21 | 547-556 | Change 1: candidate operator contract | operator entry |
| U22 | 557-571 | Change 2: reference contracts | shared contracts |
| U23 | 572-577 | Change 3: agent metadata | routing metadata |
| U24 | 578-579 | Consumer Integration | container |
| U25 | 580-587 | Change 4: task-workflow | task consumer |
| U26 | 588-619 | Change 5: convergence loop | convergence consumer |
| U27 | 620-621 | Practical Evaluator | container |
| U28 | 622-643 | Fixtures | evaluator inputs |
| U29 | 644-678 | Matrix | 13-row matrix |
| U30 | 679-771 | Evaluator exchange schemas | evaluator persistence |
| U31 | 772-817 | Exact planner and downstream outputs | agent outputs |
| U32 | 818-845 | Locked thresholds | acceptance |
| U33 | 846-847 | Tests | container |
| U34 | 848-882 | Change 6: controller and lifecycle tests | controller verification |
| U35 | 883-905 | Change 7: contract and consumer tests | integration verification |
| U36 | 906-926 | Change 8: evaluator tests | evaluator verification |
| U37 | 927-934 | Change 9: managed-skill and promotion tests | promotion verification |
| U38 | 935-936 | Candidate Installation and Evaluation | container |
| U39 | 937-957 | Change 10: candidate managed installation | candidate operation |
| U40 | 958-961 | Change 11: live practical matrix | live evaluation |
| U41 | 962-963 | Transactional Promotion | container |
| U42 | 964-1058 | Change 12: promotion controller | promotion transaction |
| U43 | 1059-1070 | Requirement Acceptance Matrix | traceability |
| U44 | 1071-1098 | Validation Commands | commands |
| U45 | 1099-1112 | Failure, Resume, and Idempotency | recovery summary |
| U46 | 1113-1128 | Ordered Execution | implementation sequence |
| U47 | 1129-1143 | Granular Approval Units | authorization |
| U48 | 1144-1165 | Closeout Checklist | terminal checks |
| U49 | 1166-1168 | One-Shot Readiness | readiness assertion |

### Complete Coverage Matrix

Every substantive unit was inspected against all ten lenses. Container rows
delegate all lenses only to the children named in their evidence.

| unit_id | ten-lens verdict | evidence |
| --- | --- | --- |
| U01 | D/R/S/F/V/G/A=NA(title); X/W/H=C | `plan.md:1-2` |
| U02 | D/R/S/F/V/G/A/X/W/H=C | Outcome and four gates are locked at `plan.md:3-16`. |
| U03 | all=NA(container U04-U05) | `plan.md:17-18` |
| U04 | all=C | Exact implementation surfaces at `plan.md:19-31`. |
| U05 | all=C | Exclusions and commit/deployment boundaries at `plan.md:32-40`. |
| U06 | all=C | Seven requirements and observables at `plan.md:41-54`. |
| U07 | all=NA(container U08-U10) | `plan.md:55-56` |
| U08 | all=C | Candidate tree and explicit-only policy at `plan.md:57-79`. |
| U09 | all=C | Ownership, isolation, lens identity, and slot closure at `plan.md:80-103`; slot states at `skills/_shared/agent_slot_ledger.py:16-18,98-176`. |
| U10 | all=C | Controller authority at `plan.md:104-124`. |
| U11 | all=NA(container U12-U19) | `plan.md:125-126` |
| U12 | all=C | Commands, state, snapshots, attempts, resume, adapters, and replay at `plan.md:127-294`; live consumer at `skills/_shared/convergence_state.py:439-501`. |
| U13 | all=C | Charter and requirement schema at `plan.md:295-320`; live fields at `skills/research-playbook/scripts/research_package.py:94-104`. |
| U14 | all=C | DIRECT and research-package boundary at `plan.md:321-354`; producer at `skills/research-playbook/scripts/research_package.py:1512-1519,1695-1769`. |
| U15 | all=C | Surface-map and decision schemas at `plan.md:355-379`. |
| U16 | all=C | Findings, dispositions, transitions, artifacts, reports, and terminal derivation at `plan.md:380-437`. |
| U17 | all=C | Profile predicate, budgets, retries, and runtime identity at `plan.md:438-450`. |
| U18 | all=C | Package authority, transaction, rollback, recovery, and replay at `plan.md:451-524`. |
| U19 | all=C | Finite verify-plan queue and ordered lenses at `plan.md:525-544`. |
| U20 | all=NA(container U21-U23) | `plan.md:545-546` |
| U21 | all=C | Task-root ownership and collision behavior at `plan.md:547-556`. |
| U22 | all=C | References, digest, slot APIs, and installer compatibility at `plan.md:557-571`; installer hashes at `working-agreement/install_skills.py:40-45,121-146`. |
| U23 | all=C | Candidate metadata and validator boundary at `plan.md:572-577`. |
| U24 | all=NA(container U25-U26) | `plan.md:578-579` |
| U25 | all=C | Task-workflow package authority, drift, invalidation, and resume at `plan.md:580-587`; predecessor at `skills/task-workflow/SKILL.md:144-189`. |
| U26 | all=C | Adapter, blockers, continuation, and transitions at `plan.md:588-619`; live schemas at `skills/_shared/convergence_state.py:439-501,585-672`. |
| U27 | all=NA(container U28-U32) | `plan.md:620-621` |
| U28 | all=C | E10-E14 and hidden-gold isolation at `plan.md:622-643`. |
| U29 | all=C | Evaluator commands and 13-row lifecycle at `plan.md:644-678`. |
| U30 | all=C | Fixture, matrix, attempt, storage, scoring, containment, and replay schemas at `plan.md:679-771`. |
| U31 | all=C | Planner and implementer schemas and nullability at `plan.md:772-817`. |
| U32 | all=C | Typed thresholds and `all_passed` derivation at `plan.md:818-845`. |
| U33 | all=NA(container U34-U37) | `plan.md:846-847` |
| U34 | all=C | Controller, lifecycle, package, crash, and replay tests at `plan.md:848-882`. |
| U35 | all=C | Routing, approval, consumer, and convergence tests at `plan.md:883-905`. |
| U36 | all=C | Evaluator isolation, lineage, scoring, and tamper tests at `plan.md:906-926`. |
| U37 | all=C | Installer and promotion recovery tests at `plan.md:927-934`. |
| U38 | all=NA(container U39-U40) | `plan.md:935-936` |
| U39 | all=C | Candidate install/probe commands and bounded changes at `plan.md:937-957`; installer at `working-agreement/install_skills.py:57-71,94-146`. |
| U40 | all=C | Practical matrix and failure boundary at `plan.md:958-961`. |
| U41 | all=NA(container U42) | `plan.md:962-963` |
| U42 | all=C | Promotion schema, ownership, journal, rollback, receipt, and verification at `plan.md:964-1058`; predecessor at `scripts/promote_research_playbook.py:129-170,392-453`. |
| U43 | all=C | R1-R7 traceability at `plan.md:1059-1070`. |
| U44 | all=C | Wrapper and evaluator commands at `plan.md:1071-1098`; wrappers at `scripts/run_pytest.sh:1-8` and `working-agreement/validate-skills.sh:1-4`. |
| U45 | all=C | Atomicity, retries, invalidation, and recovery at `plan.md:1099-1112`. |
| U46 | all=C | Ordered build, evaluation, review, approval, and promotion at `plan.md:1113-1128`. |
| U47 | all=C | Build authorization and separate promotion/commit gates at `plan.md:1129-1143`; G11 at `working-agreement/DIRECTIVES.md:154-165`. |
| U48 | all=C | Terminal checklist at `plan.md:1144-1165`. |
| U49 | all=C | Readiness assertion is supported by U02-U48 at `plan.md:1166-1168`. |

### Repository-Grounding Trace

| plan premise | repository evidence | assessment |
| --- | --- | --- |
| Slot states exist; runtime abandonment uniqueness and released-slot APIs require implementation. | `skills/_shared/agent_slot_ledger.py:16-18,98-176` | Grounded at the authoritative helper boundary. |
| Convergence consumes nested gaps, blockers, artifacts, and blocked/cap state. | `skills/_shared/convergence_state.py:439-501,585-672` | Planned adapter preserves the live consumer. |
| Research package emits six files and lacks `validate-package`. | `skills/research-playbook/scripts/research_package.py:1512-1519,1695-1769,1821-1894` | Planned validator is a bounded additive change. |
| Installer uses legacy path-plus-NUL hashes and recoverable journals. | `working-agreement/install_skills.py:40-45,74-146` | Plan preserves `source_hash` while adding `tree_sha256`. |
| Existing promotion has backup, restore, replacement, install, and candidate removal. | `scripts/promote_research_playbook.py:129-170,392-453` | Plan extends a proven transaction pattern. |
| Task-workflow owns plan creation, verification, and drift updates. | `skills/task-workflow/SKILL.md:112-189` | Consumer replacement has a concrete predecessor. |
| Convergence currently runs separate plan gates. | `skills/playbook-convergence-loop/SKILL.md:63-86` | Duplicate stages are concretely identified. |
| Routing and approval remain governed by the canonical playbook and G11. | `working-agreement/DIRECTIVES.md:16,154-165` | Promotion and commits remain separately gated. |

### Blocker Gap Ledger

| gap_id | severity | unit_id | lens | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| None | - | - | - | Fresh assessment of U01-U49 | No implementation-blocking gap found. | - | Complete matrix above | CLOSED |

### Cleanup List

| item_id | unit_id | issue | optional disposition | status |
| --- | --- | --- | --- | --- |
| CLEAN-001 | historical ledger | Historical V2-003 text mentions a superseded PLANNED count at `plan-verification-ledger.json:523`. | Preserve immutable history. | OPEN non-blocking |
| CLEAN-002 | U36 | Prior audit lacked a named evaluator test file. | Closed at `plan.md:906-926`. | CLOSED |
| CLEAN-003 | U39/U42 | Prior audit requested explicit source/installed equality. | Closed at `plan.md:956,978-993`. | CLOSED |
| CLEAN-004 | U44 | Prior focused validation omitted research-playbook tests. | Closed at `plan.md:1075-1081`. | CLOSED |
| CLEAN-005 | U34 | `covering at least` at `plan.md:850` is stylistically permissive, but mandatory cases remain enumerated. | Optional wording cleanup. | OPEN non-blocking |

### Closure Proof for GAP-001 Through GAP-007

| prior gap | closure proof | status |
| --- | --- | --- |
| GAP-001 | Attempt reservation, immutable input/token publication, slot reservation, budget accounting, finalize states, retries, caps, and replay at `plan.md:127-179,185-218,438-450`; live slots at `skills/_shared/agent_slot_ledger.py:98-176`. | CLOSED |
| GAP-002 | Outer identity and arbitrary active requirements derive from convergence state at `plan.md:276-293,588-614`; live behavior at `skills/_shared/convergence_state.py:439-501`. | CLOSED |
| GAP-003 | Internal envelopes remain distinct from exact live gap/blocker schemas, with all four deterministic mappings at `plan.md:276-293`. | CLOSED |
| GAP-004 | INLINE/FILE outputs carry exact bytes and hashes; `materialize-artifact` is the sole fixed-path writer at `plan.md:258-268,415-436`. | CLOSED |
| GAP-005 | Implementers receive only plan/package, immutable implementation sources, and case-neutral schema; hidden/evaluator/sibling authorities are excluded at `plan.md:681-689,744-768,780-816`. Scoring still requires recorded-plan agreement at `plan.md:766-770`. | CLOSED |
| GAP-006 | Existing-root ownership, PREPARING journal, backup/tombstones, stale-file handling, rollback, recovery, manifest-last commit, and replay at `plan.md:451-506`. | CLOSED |
| GAP-007 | DIRECT evidence is contained and rehashed `LOCAL_FILE|SUPPLIED_INPUT`; command/runtime evidence routes to research at `plan.md:321-353`. | CLOSED |

### Validation Evidence

| validation | result |
| --- | --- |
| Plan SHA-256 | `55fdf0a7c4d7cae5d0ecda16602b074189722cd7d773669912e82f57201ec414` before and after assessment |
| Fenced-code-aware heading scan | 49 units; U01-U49 inventoried |
| Verification ledger stop check | `OK: ledger can stop` |
| Frozen source re-hash | All active inventory dependency/evidence snapshots matched |
| Research-package re-hash | All payload hashes matched; terminal verdict `PASS` |
| JSON parsing | Ledger and research package parsed successfully |
| Flexible-word scan | No unresolved placeholder or unlocked implementation choice |
| `git diff --check` | No whitespace error |
| Repository tracing | Slot, convergence, research package, installer, promotion, consumer, wrapper, and approval premises confirmed above |
| Plan edits in Cycle 2 | None |

## Final Convergence Check

| readiness category | status | evidence |
| --- | --- | --- |
| Runtime entry points and data flow | READY | `plan.md:127-294,580-619,644-771` |
| Schemas, fields, interfaces, helpers, artifacts | READY | `plan.md:295-524,679-817,964-1041` |
| Edge cases and failures | READY | `plan.md:185-218,438-450,483-506,995-1041` |
| Resume and idempotency | READY | `plan.md:165-179,219-236,588-614,703-768` |
| Validation, tests, acceptance | READY | `plan.md:846-934,1059-1098,1144-1165` |
| Repository grounding | READY | Repository-grounding trace above |
| Approval boundaries | READY | `plan.md:1057,1129-1143`; `working-agreement/DIRECTIVES.md:154-165` |
| Out-of-scope boundaries | READY | `plan.md:32-40,580-619,935-1058` |
| Internal consistency | READY | All 49 units checked; GAP-001 through GAP-007 closed |
| One-shot implementation handoff | READY | `plan.md:1113-1168` |

**Final internal-readiness verdict: `PASS`.**

This no-edit Cycle 2 assessment found zero blocker gaps across all 49 units and
all ten lenses. It does not claim requirements breadth or end-to-end runtime
satisfaction; those remain for the next two owned gates.

## Cycle 3 Assessment

This was a fresh, no-edit, full-document INTERNAL_READINESS assessment of
`plan.md` at SHA-256
`1d770a88cac46583ad4a5e43f245b3e5eb2075888adb7316c2ad4e1cdc169ee8`.
The plan has 1,213 lines, 49 deterministic heading units, and no pre-heading
text. This cycle was required because the plan changed after Cycle 2. It
assessed the complete document rather than validating only the corrected
authorization and fixture-authority sections.

Lens key: `D` decisions; `R` runtime/data flow; `S` schemas/APIs; `F`
failure/resume/idempotency; `V` validation; `G` repository grounding; `A`
approval/scope; `X` contradictions; `W` vague choices; `H` one-shot handoff.
`ALL=C` means all ten lenses were checked and passed. Container units delegate
their checks to the named children only.

### Complete Section Inventory And Coverage Matrix

| unit | lines | section | ten-lens result | evidence |
| --- | ---: | --- | --- | --- |
| U01 | 1-2 | title | D/H=C; others=NA, title only | `plan.md:1-2` |
| U02 | 3-16 | Goal and Terminal Outcome | ALL=C | `plan.md:3-16` |
| U03 | 17-18 | Scope | NA container; U04-U05 | `plan.md:17-40` |
| U04 | 19-31 | In scope | ALL=C | `plan.md:19-31` |
| U05 | 32-40 | Out of scope | ALL=C | `plan.md:32-40` |
| U06 | 41-54 | Frozen Requirements | ALL=C | `plan.md:41-54` |
| U07 | 55-56 | Locked Architecture | NA container; U08-U10 | `plan.md:55-124` |
| U08 | 57-79 | Candidate-first development | ALL=C | `plan.md:57-79` |
| U09 | 80-103 | Parent and agent ownership | ALL=C | `plan.md:80-103` |
| U10 | 104-124 | Controller boundary | ALL=C | `plan.md:104-124` |
| U11 | 125-126 | Controller Contract | NA container; U12-U19 | `plan.md:125-559` |
| U12 | 127-299 | CLI | ALL=C | `plan.md:127-299` |
| U13 | 300-325 | Frozen charter | ALL=C | `plan.md:300-325` |
| U14 | 326-359 | Evidence entry modes | ALL=C | `plan.md:326-359` |
| U15 | 360-386 | Surface map and decisions | ALL=C | `plan.md:360-386` |
| U16 | 387-444 | Findings and gate results | ALL=C | `plan.md:387-444` |
| U17 | 445-457 | Profiles and budgets | ALL=C | `plan.md:445-457` |
| U18 | 458-539 | Plan package | ALL=C | `plan.md:458-539` |
| U19 | 540-559 | Hardening order | ALL=C | `plan.md:540-559` |
| U20 | 560-561 | Skill Contract and References | NA container; U21-U23 | `plan.md:560-592` |
| U21 | 562-571 | Candidate operator contract | ALL=C | `plan.md:562-571` |
| U22 | 572-586 | Reference contracts | ALL=C | `plan.md:572-586` |
| U23 | 587-592 | Agent metadata | ALL=C | `plan.md:587-592` |
| U24 | 593-594 | Consumer Integration | NA container; U25-U26 | `plan.md:593-639` |
| U25 | 595-602 | Task-workflow | ALL=C | `plan.md:595-602` |
| U26 | 603-639 | Convergence loop | ALL=C | `plan.md:603-639` |
| U27 | 640-641 | Practical Evaluator | NA container; U28-U32 | `plan.md:640-879` |
| U28 | 642-673 | Fixtures | ALL=C | `plan.md:642-673` |
| U29 | 674-712 | Matrix | ALL=C | `plan.md:674-712` |
| U30 | 713-805 | Evaluator exchange schemas | ALL=C | `plan.md:713-805` |
| U31 | 806-851 | Planner and downstream outputs | ALL=C | `plan.md:806-851` |
| U32 | 852-879 | Locked thresholds | ALL=C | `plan.md:852-879` |
| U33 | 880-881 | Tests | NA container; U34-U37 | `plan.md:880-972` |
| U34 | 882-918 | Controller and lifecycle tests | ALL=C | `plan.md:882-918` |
| U35 | 919-941 | Contract and consumer tests | ALL=C | `plan.md:919-941` |
| U36 | 942-964 | Evaluator tests | ALL=C | `plan.md:942-964` |
| U37 | 965-972 | Managed-skill and promotion tests | ALL=C | `plan.md:965-972` |
| U38 | 973-974 | Candidate Installation and Evaluation | NA container; U39-U40 | `plan.md:973-999` |
| U39 | 975-995 | Candidate managed installation | ALL=C | `plan.md:975-995` |
| U40 | 996-999 | Live practical matrix | ALL=C | `plan.md:996-999` |
| U41 | 1000-1001 | Transactional Promotion | NA container; U42 | `plan.md:1000-1096` |
| U42 | 1002-1096 | Promotion controller | ALL=C | `plan.md:1002-1096` |
| U43 | 1097-1108 | Requirement Acceptance Matrix | ALL=C | `plan.md:1097-1108` |
| U44 | 1109-1141 | Validation Commands | ALL=C | `plan.md:1109-1141` |
| U45 | 1142-1156 | Failure, Resume, and Idempotency | ALL=C | `plan.md:1142-1156` |
| U46 | 1157-1172 | Ordered Execution | ALL=C | `plan.md:1157-1172` |
| U47 | 1173-1187 | Granular Approval Units | ALL=C | `plan.md:1173-1187` |
| U48 | 1188-1210 | Closeout Checklist | ALL=C | `plan.md:1188-1210` |
| U49 | 1211-1213 | One-Shot Readiness | ALL=C | `plan.md:1211-1213` |

### Repository-Grounding Trace

| plan premise | repository evidence | result |
| --- | --- | --- |
| Slot reservation, unique binding, close, and release | `skills/_shared/agent_slot_ledger.py:16-18,98-176` | grounded |
| Convergence nested gaps, blockers, artifacts, and stage state | `skills/_shared/convergence_state.py:439-510,575-674` | grounded |
| Research package fixed files and requirement fields | `skills/research-playbook/scripts/research_package.py:94-104,1512-1519,1695-1769` | grounded |
| Installer journal, staging, backup, and recovery | `working-agreement/install_skills.py:94-146` | grounded |
| Existing promotion transaction predecessor | `scripts/promote_research_playbook.py:129-180,392-460` | grounded |
| Task-workflow planning and handoff ownership | `skills/task-workflow/SKILL.md:144-195` | grounded |
| Existing convergence duplicate plan gates | `skills/playbook-convergence-loop/SKILL.md:57-86` | grounded |
| Repository validation wrappers | `scripts/run_pytest.sh:1-12`; `working-agreement/validate-skills.sh:1-4` | grounded |
| Promotion, commit, and scope-expansion gates | `working-agreement/DIRECTIVES.md:154-165` | grounded |

### Blocker Gap Ledger

| gap_id | severity | unit | evidence | why blocker | planned fix | closure evidence | status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| None | - | U01-U49 | Complete ten-lens matrix above | No implementation-blocking gap found. | - | Fresh no-edit assessment | CLOSED |

### Cleanup List

| item_id | unit | issue | optional disposition | status |
| --- | --- | --- | --- | --- |
| CLEAN-001 | historical ledger | `PPV2-V2-003` retains superseded wording in immutable history. | Preserve history. | non-blocking |
| CLEAN-005 | U34 | `covering at least` is stylistically permissive, but mandatory cases are enumerated. | Optional wording cleanup. | non-blocking |

### Prior-Gap Closure Proof

| boundary | closure evidence | status |
| --- | --- | --- |
| GAP-001 pre-spawn lifecycle | `plan.md:127-299,445-457` | CLOSED |
| GAP-002 generic convergence identity | `plan.md:285-299,603-639` | CLOSED |
| GAP-003 live aggregate schemas | `plan.md:285-299,603-639` | CLOSED |
| GAP-004 FILE transfer ownership | `plan.md:258-279,387-444` | CLOSED |
| GAP-005 evaluator isolation | `plan.md:713-851` | CLOSED |
| GAP-006 existing-root transaction | `plan.md:458-539` | CLOSED |
| GAP-007 DIRECT evidence grounding | `plan.md:326-359` | CLOSED |
| Iteration 5 durable implementation authorization | `plan.md:362-383,490-496,595-639,913` | CLOSED |
| Iteration 6 reviewer identity | `plan.md:668-672` | CLOSED |
| Iteration 6 nested authority schemas | `plan.md:668-672` | CLOSED |
| Iteration 6 global runtime-agent uniqueness | `plan.md:711,948-955` | CLOSED |

The fresh assessment found no blocker, so no Cycle 3 fix plan or document edit
was required.

## Cycle 3 Validation

| validation | result |
| --- | --- |
| Plan hash before/after assessment | `1d770a88cac46583ad4a5e43f245b3e5eb2075888adb7316c2ad4e1cdc169ee8`; unchanged |
| Verification-ledger terminal check | `OK: ledger can stop` |
| Deterministic inventory | 49 heading units; all inventoried |
| Flexible-word scan | Contextual matches only; zero unlocked implementation choices |
| Whitespace validation | No `git diff --check` error |
| Repository premise trace | All cited runtime premises above confirmed |
| Plan edits in Cycle 3 | None |
| Fresh full-document blocker pass | Zero blockers |

## Final Convergence Check

| category | status | evidence |
| --- | --- | --- |
| Decision completeness | READY | U02, U06, U12-U19, U43-U49 |
| Runtime and data flow | READY | U09-U12, U18-U19, U25-U31, U42 |
| Schemas and APIs | READY | U12-U16, U18, U28-U32, U42 |
| Failure, resume, and idempotency | READY | U12, U17-U19, U26, U42, U45 |
| Validation and acceptance | READY | U32-U37, U43-U48 |
| Repository grounding | READY | Repository-grounding trace above |
| Approval and scope | READY | U04-U05, U15, U18, U25-U26, U42, U47 |
| Internal consistency | READY | All 49 units; no contradiction |
| Vague-choice elimination | READY | No unresolved implementation choice |
| One-shot handoff | READY | U46-U49 |

**Final Cycle 3 INTERNAL_READINESS verdict: `PASS`.**

This proves internal document readiness only. Requirements breadth and real
end-to-end satisfaction remain owned by the next two gates.
