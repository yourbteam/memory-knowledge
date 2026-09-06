# Requirements Machinery Atom Drive — Prototype Ledger

## Frozen measure

`winning atoms`: an atom counts only when its promoted product delta passes the closure experiment and the real operator-path confirmation recorded in `atom-drive-state.json`.

## Prototype 0 — Installed baseline

- **Hypothesis:** the repository cannot safely improve the machinery until one installed client tree is converted into a provider-neutral, managed canonical source.
- **Observed control:** the repository has no `skills/requirements-machinery` tree or managed projection entry. The installed Codex and Claude trees are unmanaged and have distinct stable tree hashes.
- **Earliest unresolved gap:** RM-00, repository ownership and deterministic client projection.
- **Candidate delta:** not yet selected; the RM-00 experiment will compare neutralized candidates derived from both captured installed trees.
- **Proof boundary:** clean projection builds for Codex and Claude from repository authority, repeated idempotently, without reading installed trees at publication time.
- **Verdict:** continue to RM-00 experiment.

## RM-00 experiment attempt 1

- **Hypothesis:** either neutralized installed tree can pass the managed publication boundary, while the later development tree preserves more already-proven corrections.
- **Observed evidence:** both variants failed before execution because the adapter read the variant envelope as the inner configuration.
- **Verdict:** revise. The failed run is preserved under `experiments/rm00/run-1`; no candidate was eligible or promoted.
- **New atom recorded, not implemented:** RM-N01 — generic experiment specifications do not hash-bind external adapter files. Successor adapters self-verify a hash declared in each variant configuration.

## RM-00 direction check after attempt 2

- **Path A — true defect on a sound approach:** keep comparing both captured lines, add lossless syntax-failure evidence to the adapter, and rerun. Evidence: all eleven newer-tree scripts compile successfully through the same Python executable outside the adapter, while its result reported one unnamed syntax failure.
- **Path B — approach cannot reach the goal:** abandon the newer line and promote the older eligible tree. This is supported only if a real script syntax error reproduces and cannot be repaired without losing its additional proven behavior.
- **Verdict:** Path A. It is additive and preserves both candidates. The verdict flips if the instrumented isolated run identifies a reproducible product syntax error rather than a measurement defect.

## RM-00 final prototype — promoted

- **Hypothesis:** the neutralized later development tree is the strongest canonical baseline because it preserves the complete fourteen-command surface, passes deterministic two-client projection, and carries more already-proven corrections than the investigated Codex tree.
- **Delta:** promoted that exact candidate to `skills/requirements-machinery`, added it to the managed manifest, and recorded its generated client-projection hashes.
- **Real evidence:** experiment run 4 selected `claude-latest`; the repository publisher then built Codex and Claude projections from the promoted tree and the installer installed both into isolated roots twice with identical hashes.
- **Verdict:** promote. RM-00 is won.
- **Remaining gap:** RM-01, the published skill contract still understates the executable requirements-production surface.

## RM-N02 prerequisite — promoted

- **Hypothesis:** the global registry fails because its declared Requirements Playbook source is absent, not because the publisher needs tolerant handling.
- **Control:** the frozen registry without that source stopped at `canonical tree missing`.
- **Candidate:** restoring the exact installed tree let the unchanged publisher regenerate all 36 entries, build both clients, and check `MATCH=36` for both.
- **Delta:** added `skills/requirements-playbook` and regenerated `working-agreement/client-skill-projections.json` from repository authority.
- **Verdict:** promote. RM-N02 is a won prerequisite; the global publisher is again a valid real-path gate.

## RM-N03 direction check after experiment run 2

- **Path A — true defect on a sound approach:** retain the schema-synchronized candidate and bind the isolated `open` command to the captured task's actual writer identity. Evidence: the control stopped at ledger line 8375, while the candidate read all 8,538 lines and reached the downstream ownership gate.
- **Path B — approach cannot reach the goal:** reject the schema candidate if the same `open` command still fails after its host identity matches the preserved ownership event.
- **Verdict:** Path A. `pre-run-blocker-ownership-mismatch` is the expected fail-closed result for an unbound process, not evidence against schema synchronization.

## RM-N03 prerequisite — promoted

- **Hypothesis:** the blocker catalog is blocked by a producer/reader contract split, not by corrupt ledger data.
- **Control:** the exact canonical command stopped at event 8,375 on `external_state_only`.
- **Candidate:** the synchronized closed schema replayed all 8,538 captured events and the same command appended one valid event under the captured owner identity.
- **Delta:** promoted the exact candidate to `scripts/work_memory.py` and added producer, validator, transition, verification, and failed-reopen regressions in `tests/test_work_memory.py`.
- **Verification:** six focused tests passed; 161 accumulated tests passed. The three remaining accumulated failures were traced to an independently dirty primary-checkout source binding and a pre-existing stale blocker-view projection.
- **Verdict:** promote. RM-N03 is a won prerequisite.

## RM-01 — promoted

- **Control:** the contract named 8 of the 14 executable commands and classified none.
- **Candidate:** one marked public-surface table names and classifies all 14 commands; `contract_surface.py` reads the same parser used by the CLI and fails closed on any inventory drift.
- **Delta:** corrected the front-door examples and product boundary, exposed a reusable parser builder, and added a repository regression.
- **Verification:** experiment parity was 14/14 with zero undocumented commands; the promoted validator and focused repository test both passed.
- **Verdict:** RM-01 is won.

## RM-02 — won

- **Control:** the exact documented command exited at argument parsing because `--quote` was absent.
- **Candidate:** the corrected example supplied every required argument, passed the real parser, and persisted the expected grounded answer.
- **Delta:** the product wording was promoted with RM-01; RM-02 added a dedicated extract-and-execute regression so example drift cannot recur silently.
- **Verification:** the controlled experiment and repository-owned CLI fixture both passed.
- **Verdict:** RM-02 is won.

## RM-03 — promoted

- **Control:** manual `answer` accepted empty, whitespace-only, and short fragment quotes; its 3/6 case score differed from the reader's existing substantive floor.
- **Candidate:** `quotecheck` owns normalization and the 25-character grounding floor, with a whole-source exception for genuinely shorter pieces; manual and reader paths call that same contract.
- **Delta:** promoted normalized validation, normalized persisted grounding, shared reader use, and the exact contract wording.
- **Verification:** the experiment passed all six manual cases, reader reflow, and shared-contract identity; three accumulated focused tests pass.
- **Verdict:** RM-03 is won.

## RM-04 — promoted

- **Control:** incomplete public output hid answer bodies and direct state exposed them, but the contract did not name that private-state boundary and completed `report` still emitted counts only.
- **Candidate:** incomplete `status` and `report` remain redacted/refused, `coverage.json` remains resumable private state, completed `report` emits the full register, and the contract explicitly denies filesystem confidentiality.
- **Delta:** promoted the exact disclosure wording, status reminder, and complete-register output.
- **Verification:** all five experiment criteria and four accumulated focused tests pass.
- **Verdict:** RM-04 is won.

## RM-05 — promoted

- **Control:** reader calls had no execution bound and ignored return codes; a process that printed `NO` and exited 7 was persisted as `does-not-bear`, while a sleeping reader hung until an outer observer killed the stage.
- **Candidate:** every call has a declared 180-second default bound, configurable only within 0–3600 seconds; timeout and nonzero exit stop with code 4 before semantic parsing, while malformed zero-exit replies retain the existing bounded semantic retry.
- **Durability:** the private feed now distinguishes `timeout`, `nonzero-exit`, `malformed-reply`, and `valid-reply`; raw stdout/stderr remain in private raw logs and diagnostics expose neither prompt nor reply.
- **Verification:** experiment run 2 passed all six frozen real-relevance-path measures against 0/6 for control; fourteen accumulated machinery/projection tests pass.
- **Verdict:** RM-05 is won.

## RM-06 — promoted

- **Control:** policy was checked only when a reader process spawned. Across eight reader-accepting commands and three state shapes, invalid commands were variously rejected by unrelated state gates, accepted on zero-call reuse, or rejected only after work began.
- **Candidate:** CLI entry validates once and replaces the string with a policy-checked identity carrying exact spawn arguments; downstream modules consume that identity without making policy depend on cached state.
- **Verification:** all 24 invalid command/state combinations produced the same policy refusal; a valid cold command spawned normally and a completed valid command emitted no reader event. The experiment passed 5/5 versus control 3/5; fifteen accumulated focused tests pass.
- **Promotion correction:** the experiment-only client policy fixture was initially copied with the candidate, caused one focused failure, and was removed before final proof; canonical source remains provider-neutral and generated client projections own client policy.
- **Verdict:** RM-06 is won.

## RM-07 — promoted

- **Control:** requirements state kept only each item's derived checkability flags; three raw replies and parsed number sets disappeared, and every resume spent the same three calls again.
- **Candidate:** a dedicated record preserves raw replies, per-line parse validation, selections, aggregate votes, dispositions, and target/prompt/item identities under one integrity hash. Items are derived from that record.
- **Verification:** the frozen real `requirements` path persisted all evidence, replayed the owner disposition byte-for-byte, resumed with zero calls, and refused a changed raw reply before spawning. The experiment passed 5/5 versus control 1/5; sixteen accumulated focused tests pass.
- **Verdict:** RM-07 is won.

## RM-08 — promoted

- **Control:** `no-answer` appeared in the relevance report but obligation extraction ignored it, so no obligation store, collapse record, owner item, or final ruling could exist.
- **Candidate:** unresolved extraction includes `no-answer`, persists its original verdict, carries the piece through collapse/distillation, and emits a stable `piece-<id>` ruling whose wording names failed reader answers rather than a false split vote.
- **Verification:** the real five-stage path reached exactly one owner item, blocked document assembly, and produced distinct admit/dismiss documents with the exact ruling in provenance. Experiment run 3 passed 5/5 versus control 1/5; seventeen accumulated tests pass.
- **Measurement corrections:** runs 1–2 exposed two adapter wording/scope errors; both captured product behavior was already correct and only the assertions changed.
- **Verdict:** RM-08 is won.

## RM-09 — promoted

- **Control:** all-negative extraction returned success without writing, so collapse saw “never run”; unresolved empty stores could advance only because they happened to contain per-piece records, with no explicit completion fact.
- **Candidate:** `obligation_completion[target]` records complete, admitted, unresolved, and processed identities separately from the obligation map. Collapse requires that fact, so absent/partial refuses while completed-empty advances.
- **Verification:** all-negative produced a zero-requirement document; all-no-answer and mixed states completed extraction but remained owner-blocked; absent state still refused. Experiment run 2 passed 5/5 versus control 1/5; eighteen accumulated tests pass.
- **Overlap recorded:** zero-result assembly required the absent-owner-map read fix anticipated by RM-13; RM-13 remains open until its own dedicated equivalence experiment passes.
- **Verdict:** RM-09 is won.

## RM-10 — promoted

- **Control:** the first dedupe stored numeric owner pairs, but requirements/distillation dropped them; assembly succeeded with no ruling.
- **Candidate:** each pair is content-addressed and carries both full source statements, piece identities, and vote evidence into a stable `source-overlap` owner item. Assembly blocks on it.
- **Verification:** repeated queue reads returned the same id; merge emitted one requirement with both pages, while keep-separate emitted two. Experiment passed 5/5 versus control 0/5; nineteen accumulated tests pass.
- **Verdict:** RM-10 is won.

## RM-11 — promoted

- **Control:** a merged pair whose shared-rule extraction failed was excluded from singles and yielded no rule, so both source duties disappeared and assembly succeeded.
- **Candidate:** the failed pair becomes a content-addressed `shared-rule` owner item containing both full sources, page identities, and all four failed attempts. No source is materialized until the owner rules.
- **Verification:** assembly blocked; `keep-both` emitted two duties, and either selection emitted exactly its chosen duty with provenance. Experiment passed 5/5 versus control 0/5; twenty accumulated tests pass.
- **Verdict:** RM-11 is won.

## RM-12 — promoted

- **Control:** identical items under Alpha and Beta targets were still presented as Step 3 Measurement Brief requirements; the prompt hash stayed identical even though the record's target field changed.
- **Candidate:** the active target appears in every prompt and the replay record binds target, prompt, and item hashes together. Only an actual Step 3 target contains that wording.
- **Verification:** three target fixtures passed all five prompt/identity measures versus control 2/5; twenty-one accumulated tests pass.
- **New atom recorded:** RM-N04 captures owner-split child votes that still lack the main pass's replay record; per the autonomy envelope it is record-only until the initial atoms are complete.
- **Verdict:** RM-12 is won.

## RM-13 — promoted

- **Control:** absent owner-ruling state raised `KeyError`, while an explicit empty map assembled; the representation, not the queue, decided success.
- **Candidate:** after the owner queue proves empty, absent and explicit-empty maps both mean zero rulings. Pending work still refuses and a completed ruling still applies.
- **Verification:** absent/explicit documents were byte-identical; pending returned the normal refusal; completed output included the ruling. Experiment passed 5/5 versus control 2/5; twenty-two accumulated tests pass.
- **Verdict:** RM-13 is won.

## RM-14 — promoted

- **Control:** exact `/tmp`, the repository root, arbitrary non-repository paths, and a symlink escape all reached state access; only slash-prefixed temp descendants were refused.
- **Candidate:** strict resolution first excludes temp roots and escapes, then the nearest `.git` directory or worktree file positively establishes containment; only nested run paths pass.
- **Verification:** eight real CLI path cases passed all five grouped measures, including a nonexistent nested child and fake worktree marker. Control passed 2/5; twenty-three accumulated tests pass.
- **Verdict:** RM-14 is won.

## RM-15 — promoted

- **Control:** source and piece hashes were write-once metadata; later commands accepted changed, missing, and extra artifacts, and `open` could replace the same work root while leaving stale files.
- **Candidate:** `open` binds an absolute source identity and exact piece manifest, refuses any pre-existing state or piece directory, and every read validates source bytes, registered piece bytes and character counts, exact filenames, file type, and UTF-8 validity.
- **Verification:** the real `open`/resume path accepted an untouched run and an independent new root, while source mutation, changed/extra/deleted pieces, and reopening the root each failed with distinct diagnostics. The experiment passed 5/5 versus control 2/5; twenty-four accumulated focused tests pass.
- **Verdict:** RM-15 is won.

## RM-16 — promoted

- **Control:** the repository carried empirical-sounding design claims and probe protocols but no claim inventory, replayable result ledger, or explicit disposition for missing historical evidence.
- **Candidate:** a source-bound manifest inventories every empirical-looking assertion and requires exactly one disposition. Verified claims must hash-bind and replay frozen input, competing variants, criteria, raw outputs, scores, environment identity, a chained ledger, and a non-automatic promotion decision; missing historical ledgers are explicitly `unverified` rather than reconstructed.
- **Verification:** the canonical and managed Codex projection reports each account for all 41 detected claims with zero omissions and 41 honest unverified dispositions. A synthetic complete ledger replayed its score, while source, manifest, frozen-input, and stored-result mutations all failed closed. Experiment run 3 passed 6/6 versus control 0/6; thirty-eight accumulated skill/projection checks plus eleven subtests pass.
- **Attempt corrections:** run 1 collided with the experiment runner's reserved `target` directory before either variant executed. Run 2 proved the mechanism in the source checkout. Final accumulated review then found that verified evidence paths were repository-rooted, so run 3 re-rooted each evidence bundle inside the projected skill and repeated the full comparison before promotion.
- **Verdict:** RM-16 is won.

## Deferred atoms — Prototype 0

- **RM-N01 reproduction:** one byte-identical frozen input and unchanged experiment specification completed twice. Changing only the adapter constant changed both variants' recorded metric from 1 to 2; the runner neither refused nor recorded an expected adapter-byte identity.
- **RM-N04 reproduction:** the real split function observed two duty-confirmation seats plus three checkability seats per child, persisted both children, and retained only `checkable`/`checkable_doubt`. Every raw and parsed checkability reply disappeared from state.
- **Verdict:** promote both reproductions as the deciding red cases. RM-N01 proceeds first because its repository authority is a prerequisite for a durable runner change; RM-N04 remains independently reproducible.
### Deferred atoms — RM-N01 controlled-comparison harness correction

- **Failed attempts:** `experiments/rmn01/run-1` launched both setups with macOS Python 3.9, which cannot import `datetime.UTC`; `experiments/rmn01/run-2` then repeated the obsolete `run <spec>` CLI shape inside the harness, so all four predeclared metrics were zero.
- **Classification:** execution error in the experiment harness, not evidence for or against RM-N01.
- **Stable correction boundary:** `experiments/rmn01/harness-source/adapter.py` now invokes the real runner CLI as `--spec <path> --output <path>`; the outer specification binds the active Python 3.14 executable.
- **Catalog exception:** the blocker-catalog ledger requires a real work-memory run or task ownership event; this local prototype has neither, so no authority identity was fabricated.

## RM-N01 — promoted

- **Control:** an unchanged version 1 specification accepted changed adapter bytes and produced a different result without any adapter identity in its ledger.
- **Candidate:** every version 2 variant binds the launched adapter's exact path and SHA-256. All adapters are checked before output creation, each hash is recorded at experiment and variant start, and mid-run drift makes the result ineligible. Unbound version 1 specifications refuse explicitly.
- **Verification:** controlled run 4 scored candidate 4/4 versus control 1/4. Three focused regression tests pass; both managed Codex and Claude staging copies pass the unchanged/change/legacy proof; twenty-three accumulated skill/projection tests pass.
- **Verdict:** RM-N01 is won.

## RM-N04 — promoted

- **Control:** split children retained only `checkable` and `checkable_doubt`; raw replies, malformed attempts, parsed choices, and the aggregate could not be replayed after restart.
- **Candidate:** the shared checkability module now builds an integrity-bound binary record for each split child. It preserves every full raw attempt and validation outcome, parses the final choice, aggregates YES/NO/invalid seats, and binds target, prompt, item, and record hashes. Malformed seats become owner doubt instead of an implied NO.
- **Resume and tamper boundary:** every state read replays each split-child record and checks its derived flags before any reader may run. Missing legacy records, changed evidence, and derived-field drift refuse with the affected child identified.
- **Verification:** controlled run 1 scored candidate 5/5 versus control 1/5. The real-state regression proves successful split, malformed-then-valid persistence, zero-call restart, and tamper refusal. Both managed Codex and Claude staging copies pass all five gates; forty-three accumulated machinery, experiment, skill, and projection tests pass.
- **Verdict:** RM-N04 is won.

## Four-atom revalidation — direction check

- **Path A — true defects on a sound approach:** preserve the existing successful controls and close four independently reproduced boundary failures. The frozen experiments show intact adapter, policy-control, and split state behave correctly while the exact adversarial cases fail the approved outcome.
- **Path B — the validation approach manufactures work:** discard the findings if the canonical operator paths reject the adversarial cases or the positive controls fail identically.
- **Verdict:** Path A. Two unchanged frozen runs reached the real runner, generated projection CLI, and split restart paths; every positive control passed and every alleged gap reproduced. The verdict would flip only if the canonical path stopped reproducing under the same frozen inputs.
- **Next prototype:** RM-N05, generated reader-policy compatibility.

## RM-N05 — promoted

- **Control:** fresh generated Codex and Claude policies omitted the reader command required by their consumer; both stopped as invalid before state access.
- **Candidate:** the shared client-policy contract now owns the recommended command, validates the exact generator shape, emits it into both projections, and uses it in the installed boundary text.
- **Verification:** the frozen experiment selected the candidate at 2/2 accepted clients versus 0/2 for control; both real projected CLIs reached the no-state boundary, and three focused repository checks passed.
- **Verdict:** RM-N05 is won.
- **Remaining gap:** RM-N06, adapter attestation must bind the bytes actually launched.

## RM-N06 — promoted

- **Control:** honest, decoy, and symbolic-link declarations all ran; a non-executed decoy could become eligible provenance and the ledger had no executed snapshot identity.
- **Candidate:** version 2 commands now have one executable adapter operand, reject symbolic links, snapshot the verified bytes per variant, launch only that snapshot, and record the actual launch command and snapshot hash.
- **Verification:** the frozen experiment selected the candidate at 4/4 versus control 1/4; four focused runner regressions pass.
- **Verdict:** RM-N06 is won.
- **Remaining gap:** RM-N07, restart must reconcile a complete persisted split graph.

## RM-N07 — promoted

- **Control:** an intact split resumed, but removing a child's lineage and evidence, blanking its statement, or unlinking the parent all resumed as valid state.
- **Candidate:** each split ruling persists one hashed graph binding its decision and target to the exact parent index, parent links, child indexes, child statements, and child checkability-record hashes. Every read reconciles the graph and rejects orphaned split markers.
- **Verification:** the frozen experiment preserved the intact restart and controlled-refused all three independent lineage mutations before any resumed reader call. Candidate scored 3/3 adversarial refusals and 0 unsafe accepts; control scored 0/3 and 3 unsafe accepts. All seventeen focused machinery tests pass.
- **Verdict:** RM-N07 is won.
- **Remaining gap:** RM-N08, malformed persisted evidence must always become a named controlled refusal instead of an internal exception.

## RM-N08 — promoted

- **Control:** an intact record resumed, but truthy string and list record containers escaped as `AttributeError`; other malformed shapes refused generically without identifying the affected child.
- **Candidate:** replay first validates the exact binary-record, seat, attempt, aggregate, hash, and field-type shapes. The split boundary wraps every invalid record with its target and child index while preserving the original reason.
- **Verification:** the frozen experiment preserved the intact restart and controlled-refused all six malformed JSON forms with the affected child named and zero resumed reader calls. Candidate scored 6/6 named refusals with zero crashes; control scored 1/6 with two crashes. All seventeen focused machinery tests pass.
- **Verdict:** RM-N08 is won.

## Session-wide promotion and installation

- **Promoted scope:** all 25 completed atoms: RM-00 through RM-16 and RM-N01 through RM-N08.
- **Managed client artifacts:** `experiment-machinery`, `requirements-machinery`, and `requirements-playbook` were regenerated from repository authority and transactionally installed into both Codex and Claude. RM-N03 remains a repository-owned work-memory repair with no client skill installation surface.
- **Installed verification:** all three selected projections report `MATCH` for both clients; both installed Requirements Machinery copies accept their generated reader command and reach the expected no-register boundary; both installed Experiment Machinery copies reran the frozen RM-N06 comparison and selected the candidate at 4/4.
- **Preserved scope boundary:** five unrelated pre-existing client drifts were not installed or changed.
- **Verdict:** session-wide promotion and installation are complete. Historical experiment summaries retain `promotion_applied: false` because experiments never self-promote; this record binds the later explicit promotion and installation.
