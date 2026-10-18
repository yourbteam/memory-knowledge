# workflow-resume-from-phase-live-confirmation

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

After an approved shared adapter edit, run `python3 scripts/regenerate_intake_contracts.py`
in report-only mode before launching. For hash-only drift, regenerate with `--write`.
For an interface change, verify it is inside the approved scope and the focused adapter
test passes, then name that one sequence with `--accept-interface-change` and `--write`.
Do not use `--accept-interface-change` for a hash-only refresh.

## Use When

A persisted United Partners workflow must continue from its exact first unfinished phase, or both held Step 5 through Step 9 or Step 11 pages must close into a verified Maria ZIP.

## Outcome

Resume a persisted United Partners workflow from its first unfinished phase, preserve completed phase state, stream the structured watcher feed, and end at completion or the first persisted deviation. For Step 5 through Step 9 and Step 11 after both explicit holds, find the exact saved runs and build or verify their Maria ZIP without operator path selection. For Step 10, resume from the exact held Step 9 child, produce the measurement report and executive scorecard, and stop at the Step 10 human review gate. The Step 11 recorded route selects the accepted Step 10 pair, records a named hold against both saved pages, and closes or verifies the package.

## Required Inputs

- A persisted non-completed United Partners workflow run.
- The exact first unfinished phase id reported by that run.
- A client key whose configured workflow matches the source run.
- The machine repository-roots authority at `~/.config/memory-knowledge/repositories.json`
  must map `united-partners` to the real United Partners repository before selecting this
  cross-repository sequence.
- The managed Python runtime and command-backed role adapter for live execution.
- Write authority for the client's persisted state directory.
- For a signed Step 1 operator review: the matching `Tasks/<client>-step1-clean-demo`
  copy, its completed operator-review source run, and the existing signed Word reply.
- For a Step 9 native-writer rehearsal: the named `Tasks/<client>-rehearsal-demo` copy,
  with its selected source run; the official client state is not the rehearsal target.
- For an automatic Step 9 or Step 11 writer confirmation: the named
  `Tasks/<client>-rehearsal-demo` copy, with its first-unfinished compose phase,
  saved upstream state, and any required approved Step 11 decision record.
- For the current Step 9 to Step 10 continuation: the exact
  `Tasks/<client>-step9-clean-<step8-root-run-suffix>` copy, its unique validated held Step 9
  child, and the first unfinished Step 10 compose or measurement-gate boundary. The Step 8
  root remains the clean-copy manifest source; the held Step 9 child remains the Step 10 writer source.
  The pair-wide writer-attempt ledger is fixed at 60 and shared by both clients.
- For a current Maria-accepted Step 10 to Step 11 continuation: the registered
  `accepted-step10-for-step11` route selects the accepted Word pair and a
  source-bound `Tasks/<client>-step11-clean-<accepted-step10-run-suffix>` copy.
  A fresh copy that stops at `measurement-gate` accepts an explicit named
  `step10_held_by` and `step10_hold_reason`; the harness binds that hold to its
  exact admitted pages before resuming the gate. The dated 20261002 copy remains
  a historical source, not the default selection for a new accepted pair.
- For Step 3 after held Step 2: the exact `Tasks/<client>-step3-clean-<accepted-step2-run-suffix>`
  copy prepared by `scripts/prepare_step3_clean_copy.py` from the current Maria Step 2
  package receipt, with old page feedback
  and signatures removed, the ancestor-decision boundary marked, and durable
  client field decisions retained. A later Step 3 gate child stays in this same copy;
  the controller verifies its ancestry against the manifest's Step 2 source.
- For Step 4 after passed Step 3: the exact
  `Tasks/<client>-step4-clean-<passed-step3-run-suffix>` copy. The ordinary
  driver prepares it from the current Step 3 copy and verifies the source
  state, lineage and manifest before the first research compose phase. A
  blocked current Step 3 gate authorizes no new Step 4 copy.
- For Step 4 interview evidence arriving after a research draft: the same exact
  clean copy, a blocked child whose completed research compose has a passed part
  ledger and whose research gate records primary research as missing, plus
  `record/primary-research-<child-run-id>.json` in that copy. The controller
  reopens only the research compose with this file. The harness checks its
  dipstick and retains unchanged research sections; the resulting pack still
  waits for a person's validation.
- For the Step 4 tier and research-rule correction: the same exact clean copy
  and a completed v3 research draft whose passed parts and document check were
  blocked at the research gate solely because the old rule demanded interviews.
  Reopen the compose with no interview file. The controller resolves B Team's
  saved combined tier to Standard only when its standing owner declaration says
  Standard; Vivacom remains Regulated. The harness reuses passed research parts,
  records missing primary research as pending for Regulated, and still requires
  a person's validation.
- For the new Step 4→Step 5 handoff: select a passed Step 4 run inside its
  admitted, source-root-named Step 4 copy and start at `compose-insight-cards`.
  The ordinary driver creates or reuses
  `Tasks/<client>-step5-clean-<selected-run-suffix>`; its v2 manifest binds the
  selected Step 4 state path and bytes, the admitted Step 4 manifest, client,
  immutable clean root bytes, first phase and shared 60-call ceiling. Any passed
  descendant in that admitted Step 4 copy can be selected; blocked, stale or
  out-of-lineage runs are refused before calls. Existing dated Step 5 copies
  remain available under their v1 manifests.
- For a Step 5 start from Maria's accepted card, give the semantic intake
  `accepted-step5-source` as the source run, the client, `compose-insight-cards`,
  and re-open no. The controller asks the harness to resolve the active,
  hash-bound document decision and its exact Step 4 source. It starts a new
  Step 5 copy only when none exists; otherwise it selects the unique saved
  child and its first unfinished phase. A held pack returns `already held`
  without another writer call until both clients are held; then the same
  ordinary resume dispatches the harness package closeout. It checks exact
  saved runs and holds, verifies an existing matching ZIP or builds one, and
  returns its path and hash. Competing child branches are refused.
  The harness admits historical v3 or compatible clean-Step-4 v4 copies,
  checking source bytes, the Step 4 manifest and accepted-card event before
  any writer call. Changed or incompatible source files are refused. An approved
  call-budget increase
  uses that preparer's `--verify-copy`, `--resume-run-state`, and
  `--extend-call-budget` inputs on the exhausted child. The append-only receipt
  binds the prior receipt, exact child bytes, spent writer-plus-board calls, and
  new ceiling; the ordinary resume checks it before any new model call.
- For Step 7 after a held Step 6 review: the current source-run-named
  `Tasks/<client>-step7-clean-<held-Step-6-run>` copy, whose manifest binds the
  held source, clean state, 60-call ceiling and `narrative-gate` stop. Older
  dated copies remain readable only for their exact recorded source.
- For Step 8 after a held Step 7 review: use `held-step7-for-step8` to select
  the current held source. The harness creates the source-named
  `Tasks/<client>-step8-clean-<source-id>` copy and binds the held source,
  clean state, 60-call ceiling and `platform-architecture-gate` stop.
- For Step 9 after a held Step 8 review: use `held-step8-for-step9` to select
  the current held source. The harness creates the source-named
  `Tasks/<client>-step9-clean-<source-id>` copy and binds the exact held source,
  clean state, 30-call ceiling per client and `toolkit-ship-gate` stop. A named
  altitude holder check is accepted only at that gate. A separate named human
  hold binds the passed toolkit and its filed Word/PDF pages; both client holds
  allow the ordinary route to create or verify the Maria ZIP.
  The two Step 8 operating calls are checked before any Step 9 writer call.
  When a saved toolkit stopped before writing or reached the ship gate with
  those calls open, the same intake takes Maria's exact newsroom choice, the
  named earned-pipeline producer and cadence, and the person who decided. The
  harness admits only the exact source-bound stop, preserves its writer cache
  and ceiling, then resumes or reopens toolkit compose as appropriate. An
  unanswered call is never inferred from the draft. A review draft
  carrying unverified research names prints their pending condition and cannot
  continue into operational phases as if they were cleared.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| preflight-resume-driver | env PYTHONPATH=src /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --help | The driver exposes --resume-run and --from-phase together. | Run in the united-partners repository with the existing managed Python runtime. |
| resume-signed-step1-review | The semantic intake selects the matching Step 1 clean copy, its blocked source run, the signed Word reply, `operator-review-of-pre-engagement-pack`, and re-open yes. | The ordinary harness reader records the three signed decisions against that source, then reruns the operator review inside the copy. | The adapter refuses a different client, copy, phase, source, or competing route. Drive staging remains in the copy; the driver verifies the reply's client and decision text. |
| resume-from-first-unfinished-phase | env PYTHONPATH=src 'UP_HARNESS_AGENT_COMMAND=/Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/codex_role_command.py' UP_HARNESS_AGENT_MAX_ATTEMPTS=3 UP_HARNESS_AGENT_TIMEOUT_SECONDS=600 UP_HARNESS_CODEX_TIMEOUT_SECONDS=600 /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --client <client> --resume-run <persisted-run-id> --from-phase <first-unfinished-phase> | A new child preserves every completed source phase, starts at the named first unfinished phase, streams watcher activity, and reaches completion or one persisted diagnosable deviation. | The driver validates the workflow identity and boundary before model work and launches scripts/watch_run.py automatically. |
| resume-automatic-writer-on-copy | The semantic intake supplies client, the exact `Tasks/<client>-rehearsal-demo` folder, a saved source run, `compose-execution-toolkit` or `compose-annual-review` as its first unfinished phase, and no writer override, call-limit answer, or saved-cache continuation choice. The adapter dispatches an ordinary resume with `--task-dir` pointing to that copy. | The current harness automatically selects its Step 9 or Step 11 writer, with its own persisted call ceiling and recovery identity; state, artifacts, and Drive staging stay in the copy. | The adapter rejects official or mismatched folders, other resume input files, and re-opening a completed phase. It clears external Drive access and limits provider attempts to one per writer call. |
| prepare-clean-step11-copy | The registered `accepted-step10-for-step11` route selects the current accepted Step 10 pair. | It prepares a source-bound clean copy, records admission and resumes only the first unfinished phase. | A stale source or a different client copy is refused before model work. |
| admit-accepted-step10-for-clean-step11 | The semantic intake selects the exact dated clean copy, the selected Step 9 run, `compose-measurement-framework`, re-open yes, and its `record/step10-admission.json`. | The ordinary harness admits only the exact accepted Step 10 pages, then reaches the first human gate or the next compose. | The adapter rejects the official and old rehearsal folders, another phase, or other resume inputs. |
| carry-step10-holder-check-into-clean-step11 | At an `awaiting-step10-hold` route, the semantic intake takes the explicit `step10_held_by` and `step10_hold_reason`. | The harness checks the accepted Word pair against the blocked compose, records the holder decision and resumes only `measurement-gate`. | No hold is inferred from acceptance; missing, stale or changed pages are refused. |
| carry-step11-holder-check-into-clean-copy | The semantic intake selects the dated clean copy, the saved Step 11 compose run, `annual-review-gate`, re-open no, and its `record/annual-review-altitude-check.json`. | The ordinary gate checks the holder's verdict against the exact new Step 11 review before proceeding to certification and export. | The check must name the exact Step 11 compose run; the harness validates it. The controller refuses another phase or input file. |
| resume-clean-step11-automatic-writer | The semantic intake selects the dated clean copy, the first-unfinished `compose-annual-review` source run, re-open no, and leaves admission and holder files blank. | The normal source-bound Step 11 writer runs within its persisted call ceiling in the copy. | The controller refuses a completed-phase rewind and keeps Drive staging inside the copy. |
| prepare-clean-step3-copy | env PYTHONPATH=src /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/prepare_step3_clean_copy.py --client <client> | The current Step 2 source named by the accepted Maria package is copied into a source-run-named Step 3 folder with source and receipt hashes; old Step 3 page edits/signatures are removed and ancestor feedback is excluded. | Guard the checked-in script. The managed Python includes the harness's document dependencies; it refuses mismatched source pages or differing existing files. An ordinary resume also prepares the copy if absent. |
| resume-clean-step3-native-writer | The semantic intake selects the source-run-named Step 3 copy, its accepted Step 2 run, `compose-final-brief`, re-open no, and leaves feedback/approval files blank. | The normal checkpointed Step 3 writer composes parts, creates the Word/PDF pair, runs the CFO/Journalist board, and parks at final-brief-gate. | The controller and driver refuse another client folder, stale Step 2 source, changed manifest or a phase outside Step 3; Drive staging stays in the copy. Historical dated copies remain available at their human gate only. |
| resume-clean-step4-native-writer | The semantic intake selects the source-run-named Step 4 copy, its current passed Step 3 source run, `compose-research-insight-pack`, re-open no, and leaves feedback/approval files blank. | The ordinary driver prepares and admits the copy before model work; the checkpointed Step 4 writer composes research parts, creates the Word/PDF pair, and parks at research-gate. | The controller checks the copy manifest and source-state hash, refuses a different client or phase, limits provider attempts to one per writer call, and keeps Drive staging inside the copy. Historical dated copies remain available at their human gate only. |
| record-step4-source-hold | `python3 scripts/record_step4_review_hold.py --client <client> --run <step4-run-state> --held-by <reviewer> --output <clean-copy-record-path> --confirmed-held` | A typed receipt binds the explicit hold to the exact Step 4 run, research content, Word, PDF, gate state and unresolved condition. | Run only after the named reviewer explicitly holds the generated page pair. The script refuses changed or incomplete files. |
| prepare-clean-step5-copy | For an accepted-card start, continuation, or held closeout, the semantic intake supplies `accepted-step5-source`, client, `compose-insight-cards`, re-open no, and no competing route inputs. | The harness resolves the accepted Step 4 source and unique saved Step 5 leaf. It prepares a new copy only when absent; otherwise it resumes the first unfinished phase. When both clients are held, the controller dispatches the harness package closeout, which returns the verified ZIP path and hash. | Held packs make no writer call. A changed source, incompatible accepted card, ambiguous branch, missing second hold, or altered ZIP is refused. |
| resume-clean-step5-native-writer | The semantic intake selects the source-run-named Step 5 copy, its root or exact saved descendant, the first unfinished Step 5 phase, re-open no, and leaves other routes blank. A completed phase may be explicitly reopened only from its saved descendant. | The normal checkpointed Step 5 writer preserves accepted parts, mini-board checkpoints, failed or in-flight attempts, and cumulative writer-plus-board calls, then parks at `insight-gate`. | The controller checks source/root hashes, client and descendant lineage before dispatch; accepted-source v3 and v4 copies use the harness's admission check. The combined ceiling remains 60 calls per client and Drive staging stays inside the copy. |
| record-step5-review-hold | `python3 scripts/record_step5_review_hold.py --client <client> --run <step5-run-state> --held-by <reviewer> --output <clean-copy-record-path> --confirmed-held` | A typed receipt binds the explicit hold to the exact Step 5 content, mini-board report and every generated Word/PDF file. | Run only after the named reviewer explicitly holds the generated files. |
| close-held-step5-package | The same `accepted-step5-source` resume answer after both explicit holds dispatches `python3 -m up_harness.step5_maria_package --close-recorded`. | The harness locates the unique saved held runs and their hold receipts, verifies an existing matching Maria ZIP or builds it once, and reports its path and hash. | A missing hold, changed source, altered ZIP, or competing matching package is refused before creating output. No writer call is made. |
| build-step5-maria-package | `python3 -m up_harness.step5_maria_package --bteam-run <bteam-state> --vivacom-run <vivacom-state> --bteam-review-hold <bteam-hold> --vivacom-review-hold <vivacom-hold> --output <package-dir> --receipt <receipt-path>` | The harness writes and reopens the complete Maria ZIP, verifies every member against its receipt, and returns the ZIP hash and file count. | The package refuses missing/stale holds, changed parts, stale mini-board evidence, or unbound Word/PDF files. |
| prepare-clean-step6-copy | `python3 scripts/prepare_step6_clean_copy.py --client <client> --source-run-state <step5-run-state> --source-review-hold <step5-hold-path> --output <dated-step6-copy>` | Admit the exact held Step 5 files in an isolated Step 6 copy; preserve pending insight selection and audience testing. | No source page is changed; a changed hold or document is refused. |
| resume-recorded-step6-writer | The semantic intake uses source `held-step6-source`, client, `compose-strategy-one-pager`, re-open no, and leaves other inputs blank. | The harness resolves the current held Step 5 leaf, creates or admits its source-run-named Step 6 copy, then resumes the exact first unfinished Step 6 phase inside that copy. | A stale Step 5 source, changed copy manifest, wrong client, or ambiguous continuation is refused before model work. Drive staging stays in the copy. |
| record-recorded-step6-hold | The same semantic route after the Step 6 gate is ready, with `step6_held_by` set to the reviewer who explicitly held the exact saved page. | The harness writes a content-bound hold without page or run paths. If the other client is already held, it builds or verifies the Maria ZIP in the same resume. | A missing explicit reviewer, incomplete page, changed Word/PDF, or conflicting prior reviewer is refused. No model call is made. |
| close-recorded-step6-package | The same semantic route after both Step 6 pages are held, with `step6_held_by` blank. | The harness locates both saved runs and holds, verifies an existing matching 16-file ZIP or builds it once, and returns its path and hash. | A missing hold, changed source, altered ZIP member, or competing matching package is refused. No model call is made. |
| resume-clean-step6-native-writer | The semantic intake selects `Tasks/<client>-step6-clean-20261006`, its source run, `compose-strategy-one-pager`, re-open no, and leaves other routes blank. Subsequent blocked or failed compose children resume from their saved ledger; a completed phase can be explicitly reopened after its logic changes. | The ordinary harness preserves valid parts and spent calls, repairs only the owning part, renders Word/PDF and stops after `strategy-approach-gate`. | The manifest, source hold, root-state hash and child lineage bind the route; Drive output stays inside the copy; 60 shared writer calls per client. |
| record-step6-review-hold | `python3 scripts/record_step6_review_hold.py --client <client> --run <step6-run-state> --held-by <reviewer> --output <copy-record-path> --confirmed-held` | Bind the explicit held decision to the final saved page and Word/PDF bytes. | The held decision does not select the strategic approach or public expression. |
| build-step6-maria-package | `python3 -m up_harness.step6_maria_package --bteam-run <bteam-state> --vivacom-run <vivacom-state> --bteam-review-hold <bteam-hold> --vivacom-review-hold <vivacom-hold> --output <package-dir> --receipt <receipt-path>` | Build and reopen the full two-client Maria ZIP, checking every member hash. | Reject stale sources, parts, documents, failed gates and mismatched holds. |
| resume-recorded-step7-writer | The semantic intake uses source `held-step6-for-step7`, client, `compose-big-idea`, re-open no, and leaves other inputs blank. A blocked child resumes from the saved phase using its current clean copy. | The harness resolves the current held Step 6 leaf, creates or admits its source-run-named Step 7 copy, then writes inside that copy under the shared 60-call ceiling. | A stale source, changed manifest, wrong client, or ambiguous continuation is refused before model work. Drive staging stays in the copy. |
| record-recorded-step7-hold | The same semantic route after the Step 7 narrative gate, with `step7_held_by` naming the reviewer who explicitly held the page. | The harness records a content-bound hold and builds or verifies the Maria ZIP when the other client is held. The exact hold command validates the saved source and document hashes, so it does not repeat the broad resume test suite. | An incomplete page, changed Word/PDF, or conflicting prior reviewer is refused. No model call is made. |
| close-recorded-step7-package | The same semantic route after both pages are held, with `step7_held_by` blank. | The harness locates both saved runs and holds and builds or verifies the complete Maria ZIP without file-path selection. The exact closeout command validates the ZIP members and receipt, so it does not repeat the broad resume test suite. | A missing hold, changed source, altered ZIP member, or competing matching package is refused. No model call is made. |
| resume-clean-step7-native-writer | A blocked or failed Step 7 child can resume its saved phase from its current source-bound clean copy; typed section feedback in that copy's `record` folder enters at `compose-message-architecture`. Historical dated copies remain bound to their original manifests. | The ordinary harness resumes only the unfinished Step 7 work and stops after `narrative-gate`. | The adapter checks source binding, clean-state hash and child lineage before model work. |
| resume-clean-step8-native-writer | The semantic intake asks for repository, client, `held-step7-for-step8`, and an optional named reviewer. Leave the reviewer blank to start or resume the saved writer. The controller supplies the canonical compose phase and no-reopen answer; a saved child stays in its source-bound copy. | The ordinary harness selects the current held Step 7 page, composes the communications platform with a durable 60-call ceiling, saves its Word/PDF pair and stops after `platform-architecture-gate`. | The adapter checks the exact held Step 7 source, clean-state hash and child lineage; it rejects a different folder, phase, or mixed route before model work. Writer resumes retain the regression preflight and keep Drive staging inside the copy. |
| record-recorded-step8-hold | The same four-question semantic route after the Step 8 architecture gate, with the reviewer naming the person who explicitly held the page. | The harness records a content-bound hold and builds or verifies the Maria ZIP when the other client is held. The exact hold command checks its saved source and document bytes, so it skips the broad resume suite. | A missing reviewer, incomplete page, changed Word/PDF, or conflicting prior hold is refused. No model call is made. |
| close-recorded-step8-package | The same four-question semantic route after both Step 8 pages are held, with the reviewer blank. | The harness locates both saved runs and holds and builds or verifies the complete Maria ZIP without file-path selection. The exact closeout checks the ZIP members and receipt, so it skips the broad resume suite. | A missing hold, changed source, altered ZIP, or competing package is refused. No model call is made. |
| resume-clean-step9-native-writer | The semantic intake uses `held-step8-for-step9`, client and `compose-execution-toolkit`, with re-open no. Leave the reviewer and altitude file blank to start or resume the saved writer. | The harness selects the current held Step 8 page and resumes only Step 9 inside its source-bound copy, with 30 writer calls per client and local Drive staging. | Changed Step 8 source, hold, clean-state manifest, client identity or child lineage is refused before a new writer call. |
| carry-step9-holder-check | On a blocked `toolkit-ship-gate` child, use the same recorded route with a `toolkit-altitude-check.json` file in that copy's record folder. | The ordinary gate checks the named holder's verdict against the saved toolkit and then stops at Step 9. | No earlier phase or different copy can receive the check. The check does not itself record a human review hold. |
| record-recorded-step9-hold | When the Step 9 ship gate has passed, use the same recorded route with `step9_held_by` naming the person who reviewed the exact toolkit. | The harness records a hold bound to the current run, Step 8 source, toolkit content and filed Word/PDF bytes. | Incomplete gate, missing files, stale content or a conflicting reviewer is refused. No model call is made. |
| close-recorded-step9-package | After both Step 9 toolkits are held, use the same recorded route with reviewer blank. | The harness builds or verifies the two-client Maria ZIP, its reading maps, source registers, checks and receipt. | Changed source, hold, ZIP member or receipt is refused. Repeated close verifies the same package without model calls. |
| resume-step4-late-interview-evidence | The semantic intake selects the exact current Step 4 copy, its blocked research-gate child, `compose-research-insight-pack`, re-open yes, and that child's `record/primary-research-<child-run-id>.json`. | The controller supplies the recorded dipstick to the ordinary resume. The harness reassembles the pack from saved research sections without repeat writer calls when only the interview evidence changed, then checks the research gate again. | The adapter rejects a wrong copy, lineage, file name, phase, or gate reason. The harness rejects invalid dipsticks and keeps human validation separate. |
| resume-step4-tier-and-research-contract | The semantic intake selects the exact current Step 4 copy, its v3 draft blocked only by the old mandatory-interview rule, `compose-research-insight-pack`, re-open yes, and no interview file. | The ordinary resume retains passed research parts, applies the current tier contract, and records missing primary research as pending only for Enterprise or Regulated. B Team's legacy combined tier is resolved to Standard from its standing owner declaration. | The adapter requires the passed 14-part ledger, document check, source lineage, exact old gate reason and owner tier declaration before dispatch. Human validation remains separate. |
| resume-step11-writer-with-shared-call-budget | env PYTHONPATH=src 'UP_HARNESS_AGENT_COMMAND=/Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/codex_role_command.py' UP_HARNESS_AGENT_MAX_ATTEMPTS=3 UP_HARNESS_AGENT_TIMEOUT_SECONDS=600 UP_HARNESS_CODEX_TIMEOUT_SECONDS=600 /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --client <client> --resume-run <persisted-run-id> --from-phase compose-annual-review --step11-writer-input-file <source-bound-writer-input-file> --step11-writer-call-budget-file <shared-writer-call-budget-file> --step11-writer-call-limit <positive-call-limit> [--step11-writer-call-extension-from <previous-limit>] | Step 11 resumes with its source-bound writer input and shared call budget. An explicitly authorized extension increases the existing ledger limit without resetting reservations. | Supply all three Step 11 settings together only at compose-annual-review; leave all three blank otherwise. Supply the optional previous limit only for an approved increase on the same ledger, with a strictly higher new limit. No other optional resume input file may be combined. |
| resume-step9-native-writer-on-copy | The semantic intake supplies client, selected copy folder, source run, `compose-execution-toolkit`, re-open yes, and a writer-call limit from 1 to 150. The adapter dispatches `scripts/run_client_regeneration.py --client <client> --resume-run <persisted-run-id> --from-phase compose-execution-toolkit --rerun-completed --task-dir <Tasks/client-rehearsal-demo> --step9-native-writer-call-limit <1-150>` with one command attempt per native writer call, Drive token and parent cleared, and Drive root inside the copy. | The native part writer composes from the selected run through the normal harness, stops at `toolkit-ship-gate`, and leaves state, artifacts, and local Drive staging inside the copy. | Supply no other resume input. The adapter and driver both reject a real client folder or a mismatched client copy before model work. The approved new Vivacom rehearsal may use up to 150 native-writer calls. |
| continue-step9-native-writer-from-saved-cache | The semantic intake selects a client, its exact Tasks/<client>-rehearsal-demo copy, compose-execution-toolkit, reopen no, saved-cache continuation yes, and leaves both call-limit and extension answers blank. | The child resumes with the persisted native-writer request and cache intact, retains the same root, used count and ceiling, and stops at toolkit-ship-gate. One per-copy lock prevents concurrent continuation dispatch. | Before dispatch, the driver requires matching client and rehearsal copy, a matching workflow/root/request/cache budget with integer 0 ≤ used < limit ≤ 150, blocked or failed compose as the first unfinished phase with no downstream phase state, and the latest continuation leaf. A stale interrupted running child is first terminalized as failed under the same per-copy lock after the identical identity and cache checks. It passes only stop_after_phase; stale, mismatched or concurrent continuations are refused.
| extend-failed-step9-native-writer-budget | The semantic intake selects B Team, failed run `up-run-9e6d9c40be19`, exact copy `Tasks/bteam-rehearsal-demo`, `compose-execution-toolkit`, reopen no, saved-cache continuation yes, and extension ceiling 60. | A child carries the native-writer request with the same root source `up-run-34918141462e`, preserves the failed run's 30 used calls and valid cached parts, extends that cache budget to 60, and stops at `toolkit-ship-gate`. The adapter keeps one command attempt per writer call and Drive staging inside the copy. | Before model work, the driver requires the exact failed run, root request and cache identity, a 30/30 budget, and the exact B Team copy. It rejects a different run/client/folder or official client path. The runner accepts this extension with reopen disabled and does not clear the cache. |
| extend-exhausted-step9-native-writer-to-150 | The semantic intake selects the latest failed 60/60 child in the exact B Team or Vivacom rehearsal copy, `compose-execution-toolkit`, reopen no, saved-cache continuation yes, and extension ceiling 150. | A child keeps all 60 spent calls, cached parts and selected Step 9 root, raising only the ceiling to 150 and stopping at `toolkit-ship-gate`. | The driver verifies the latest failed child, matching client, root request, exhausted 60/60 cache, no downstream state and per-copy lock; the runner verifies the same extension before carrying it forward. |
| resume-with-corrected-topic-policies | env PYTHONPATH=src 'UP_HARNESS_AGENT_COMMAND=/Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/codex_role_command.py' UP_HARNESS_AGENT_MAX_ATTEMPTS=3 UP_HARNESS_AGENT_TIMEOUT_SECONDS=600 UP_HARNESS_CODEX_TIMEOUT_SECONDS=600 /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --client <client> --resume-run <persisted-run-id> --from-phase prepare-controlled-topic-policy-inputs --controlled-topic-policies-file <corrected-policy-file> | The corrected all-FLAG topic policy set replaces the persisted defective one, the prepare phase re-validates it, and the run continues to completion or its next persisted deviation. | Valid only at prepare-controlled-topic-policy-inputs; the driver refuses the flag at any other resume phase. Added 2026-08-22 after a mid-sentence allowed-fact excerpt blocked a run whose corrected set had no way back in. |
| resume-with-late-arriving-answers | env PYTHONPATH=src 'UP_HARNESS_AGENT_COMMAND=/Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/codex_role_command.py' UP_HARNESS_AGENT_MAX_ATTEMPTS=3 UP_HARNESS_AGENT_TIMEOUT_SECONDS=600 UP_HARNESS_CODEX_TIMEOUT_SECONDS=600 /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --client <client> --resume-run <persisted-run-id> --from-phase prepare-controlled-topic-policy-inputs --rerun-completed --client-answers-file <answers-file> | The client's interview answers, arrived after the run settled, replace the empty set the run recorded; the answer-consuming phases re-run and the run continues to its next gate. | Valid only re-entering at prepare-controlled-topic-policy-inputs or ingest-leadership-interview; the driver refuses the flag elsewhere. Added 2026-08-22 for the B-team owners' interview, found in a legacy document after the run had settled. |
| reopen-completed-phase | env PYTHONPATH=src 'UP_HARNESS_AGENT_COMMAND=/Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/codex_role_command.py' UP_HARNESS_AGENT_MAX_ATTEMPTS=3 UP_HARNESS_AGENT_TIMEOUT_SECONDS=600 UP_HARNESS_CODEX_TIMEOUT_SECONDS=600 /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/run_client_regeneration.py --client <client> --resume-run <persisted-run-id> --from-phase <first-unfinished-phase> --rerun-completed | A phase the source already completed is discarded together with every phase after it, and re-run against current code. | Use only when that phase's own logic changed; the intake asks for it as a yes/no answer. Added 2026-07-28 after a corrected publication check could not be exercised without regenerating the whole run. |
| verify-automation | env -C /Users/kamenkamenov/united-partners PYTHONPATH=src /Users/kamenkamenov/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest tests.unit.test_workflow_resume tests.unit.test_client_regeneration_resume tests.unit.test_vivacom_phase20_reproduction tests.unit.test_codex_role_command tests.unit.test_role_executor_retry -v | Writer and other ordinary resumes run this deterministic regression suite before dispatch. Exact Step 7 and Step 8 hold and ZIP closeout commands validate their own saved files and skip this repeated suite. | The command binds its own united-partners working directory; no model call is made. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-shared-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --co-blocker-id <co-blocker-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | Use when one code change closes two blockers in this run. | Both blocker occurrences must be open and source-bound to the same run. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |
| select-correction-successor | python3 scripts/work_memory.py select-successor --predecessor-run-id <run-id> | Selects the corrected predecessor's task, sequence, repository roots, and active correction ids as one bound successor request. | Do not create a new task or manually repeat predecessor identity fields; this command derives them from the closed failed predecessor. |

## Failure Handling

Fail before model work when the source is completed, belongs to another workflow, the phase is unknown, the phase is not the first unfinished boundary, downstream state already exists, or the watcher cannot bind the emitted child identity. During execution, retain the child state and stop at the first persisted deviation; catalog and correct that stable boundary before another live successor.

## Verification

- Three real executions used the same driver: phase-20 resume from up-run-96aecc52ba4d, corrected phase-20 resume from up-run-bca4c0d9a7bf, and phase-33 resume from up-run-78d991b5036c. The deterministic resume suites provide the repeatable promotion check; a registered phase-33 successor supplies current live confirmation.

Pass signal: A new child preserves all completed source phases, begins at the requested first unfinished phase, and reaches completion or one persisted diagnosable deviation while watcher telemetry remains active.

Promoted from `2026-07-20-workflow-resume-from-phase-live-confirmation`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
