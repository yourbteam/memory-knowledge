# Sequence intake implementation blockers

## SI-001 — Registry coverage test coupled to mutable owner-source hashes

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `focused-regression`
- Practical symptom: the adapter-registry coverage test fails before returning registry IDs.
- Confirmed evidence: `work_memory.registry_rows()` rejected
  `commit-push-main` and then `greenfield-full-drive` with
  `executable-owner-source-hash-drift`.
- Practical impact: the focused intake regression cannot prove exact canonical registry coverage.
- Stable boundary: registry identity coverage must read the canonical `SEQUENCES.md` identity
  table without invoking the separate cross-repository executable-owner integrity validator.
- Solution: the test now uses `prevention_registry.parse_markdown_projection()` against the
  canonical registry file; executable-owner validation remains unchanged and independently owned.
- Verification: the same focused regression command completed with `44 passed in 4.17s`.
- Remaining work: none for this blocker.
- Catalog note: the canonical helper rejected a pre-run record with
  `exactly-one-blocker-authority-required`; this fast-path implementation has no run or ownership
  event to invent, so the task-local catalog preserves the blocker without fabricating authority.

## SI-002 — All-owner materialization blocked by unrelated greenfield source drift

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `refresh-commit-push-owner-contract`
- Practical symptom: the canonical executable-owner materializer stops before emitting any
  contracts.
- Confirmed evidence: `python3 scripts/prevention_contract_materializer.py --output
  /private/tmp/sequence-intake-owner-contracts.json` raised
  `source-correction-not-approved:/Users/kamenkamenov/mcp-agents-workflow/scripts/greenfield_drive_dag.py`.
- Practical impact: the approved `commit-push-main` proposal can be updated, but the canonical
  aggregate `owner-executable-contracts.json` cannot be regenerated or verified.
- Stable boundary: the drift is a real new `validate-fresh` behavior split across the bound CLI
  script and the currently unbound MCP consumer. Advancing only the CLI hash would approve a
  forwarding surface while leaving the behavior-producing source and owner parameter contract
  outside governance.
- Cause chain: the CLI added `--validate-fresh` and forwards `validateFresh`; the MCP server added
  the input schema and fresh-ledger behavior; the governed shell/adapter/profile/proof path still
  has only the original three modes. The aggregate materializer therefore rejects the changed CLI
  before it can refresh the independent commit/push owner.
- Verification evidence: the complete `validate-fresh` path is now bound through shell, adapter,
  source probes, durable state, contracts, and proofs; 24 external durability tests and the
  165-test focused prevention/intake suite pass. All 242 current proofs and all three generated
  artifact checks pass.
- Remaining work: none.

## SI-003 — Invalid inline Python verification shape

- Status: closed
- Type: execution error
- Task: `sequence-script-intake-core`
- Step: `verify-greenfield-payload-forwarding`
- Practical symptom: the one-line verification command raised `SyntaxError` before importing or
  exercising the script.
- Confirmed evidence: Python rejected `class R` after a semicolon in the `python -c` source.
- Practical impact: none to repository state or product behavior; the intended assertion did not run.
- Stable boundary: build inline test doubles with expression-compatible constructs, or use a
  checked-in test when the verification becomes recurrent.
- Solution: correct the invocation once using expression-built test doubles.
- Verification: superseded by the explicit temporary-module verification recorded in SI-004.
- Remaining work: none.

## SI-004 — Incomplete inline fake-client constructor

- Status: closed
- Type: execution error
- Task: `sequence-script-intake-core`
- Step: `verify-greenfield-payload-forwarding`
- Practical symptom: the corrected inline verification reached `_amain` but raised
  `TypeError: C() takes no arguments` while constructing the fake client.
- Confirmed evidence: `_amain` calls `RemoteMcpClient(_cfg())`; the expression-built fake omitted
  a compatible `__init__`.
- Practical impact: none to repository state or product behavior; payload forwarding remained
  unexecuted by this command.
- Stable boundary: use a readable temporary test module with an explicit fake-client class instead
  of compressing asynchronous collaborator behavior into `python -c`.
- Solution: replace the one-liner with that bounded temporary test module.
- Verification: `uv run python -B /private/tmp/verify_greenfield_validate_fresh.py` completed with
  `payload-forwarding-ok`; it proved the false default, true opt-in, and exact
  `validateFresh: true` MCP payload.
- Remaining work: none.

## SI-005 — Fresh evidence omitted from durable result allowlist

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `verify-greenfield-validate-fresh`
- Practical symptom: the focused greenfield suite rejected an otherwise valid
  `{"verdict":"validated","rounds":1,"fresh":true}` result.
- Confirmed evidence: `_validate_validation_result` accepted `fresh`, but the upstream
  `_VALIDATION_RESULT_FIELDS` closed-object allowlist did not; 97 sibling tests passed and the
  focused assertion failed on `unknown=['fresh']`.
- Practical impact: fresh-validation evidence could not be persisted, so the new owner profile
  could not prove that it ran a fresh smoke.
- Stable boundary: the durable state model has one closed field vocabulary used before its
  discriminated value validator; both must recognize the same evidence field.
- Solution: add `fresh` to `_VALIDATION_RESULT_FIELDS` while keeping it optional for compatibility
  with existing stored program states.
- Verification: the same focused suite completed with `98 passed in 0.99s`.
- Remaining work: none.

## SI-006 — Prevention tests invoked outside the managed environment

- Status: closed
- Type: execution error
- Task: `sequence-script-intake-core`
- Step: `verify-greenfield-owner-contract`
- Practical symptom: the prevention test command exited before collection with
  `No module named pytest`.
- Confirmed evidence: system `/opt/homebrew/opt/python@3.14/bin/python3.14` lacks pytest.
- Practical impact: no prevention tests ran; repository or runtime state was unaffected.
- Stable boundary: use this repository's managed `uv run pytest` test entry point.
- Solution: rerun the unchanged focused test selection through `uv`.
- Verification: `uv run pytest` collected and ran the selected prevention tests; its failures were
  the separately catalogued stale-generated-contract condition SI-007.
- Remaining work: none.

## SI-007 — Generated owner contracts predate approved proposal changes

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `verify-greenfield-owner-contract`
- Practical symptom: 35 prevention tests failed while loading the typed registry or materializing
  owners.
- Confirmed evidence: the first registry error was
  `executable-owner-proposal-hash-drift:commit-push-main`; direct materialization then reported the
  immediately stale greenfield program-state source hash after SI-005 changed its allowlist.
  The first observable-generation attempt later rejected the MCP-server binding because its hash
  had been captured before the final invalid-mode guard was added; all four final source hashes
  were then recalculated together. During selector work, upstream `mcp-agents-workflow` advanced to
  commits `f6494ffe` and `07da6696`; the validated behavior remained present but the committed MCP
  server hash became `2aa61e3b...`, requiring one final binding refresh.
- Practical impact: tests that depend on the canonical generated aggregate cannot load either
  changed proposal until the aggregate is regenerated.
- Stable boundary: proposal changes and final implementation-source hashes must be settled before
  generating `owner-executable-contracts.json`; dependent tests run only against that generated
  state.
- Solution: update the final greenfield program-state hash, run the canonical all-owner
  materializer, and then rerun the same focused owner suite.
- Verification: executable contracts materialized at
  `5eb2c6c7...`, source verification at `f939bbfb...`, and observable evidence at
  `c272cdc6...`; all three canonical `--check` commands pass.
- Remaining work: none.

## SI-008 — Immutable proof history rejects successor traces

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `regenerate-greenfield-owner-proofs`
- Practical symptom: adding the required `validate-fresh` provider changes the shared provider
  implementation hash, so successor traces are required; the assembler currently rejects any old
  and new trace pair for the same owner/profile/proof as `owner-proof-trace-duplicate`.
- Confirmed evidence: `_scan_traces()` indexes only by
  `(owner_sequence_id, profile_id, proof_kind)` and raises on a second content-addressed file,
  while trace identity validation later includes contract-policy and provider hashes. The artifact
  directory is untracked and already contains 258 immutable traces, so deleting it would destroy
  prior evidence that is not ours to discard.
- Practical impact: greenfield proofs cannot be regenerated without either deleting historical
  evidence or teaching the assembler to select the trace for the current contract/provider.
- Stable boundary: immutable proof corpora must permit successor versions and select exactly one
  trace whose contract, policy, provider, source, and case identities match the current assembly.
- Verification evidence: stale traces remain immutable, current candidates are fully validated,
  equivalent repeated executions choose a stable content hash, missing current traces still fail
  closed, and the real second generator pass executed zero scenarios while selecting 242 proofs.
- Remaining work: none.

## SI-009 — Provider-map assertions displaced during selector test insertion

- Status: closed
- Type: execution error
- Task: `sequence-script-intake-core`
- Step: `verify-proof-successor-selection`
- Practical symptom: the ambiguity test passed its expected exception and then raised
  `NameError: expected is not defined`.
- Confirmed evidence: two assertions belonging to
  `test_production_provider_map_is_immutable_and_complete_for_all_profiles` were left below the new
  ambiguity test during insertion.
- Practical impact: one targeted test failed after the selector behavior had already passed.
- Stable boundary: keep the provider-map completeness/immutability assertions in their original
  test; the selector tests assert only successor selection and ambiguity.
- Solution: move the two assertions back without changing implementation behavior.
- Verification: pending the same three-test rerun.
- Remaining work: none.

## SI-010 — Credential-owner acceptance source exceeds fixed timeout

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `regenerate-owner-acceptance-proofs`
- Practical symptom: the no-input batch stopped on its first profile after 60 seconds with no
  source output.
- Confirmed evidence: `claude-auth-token-refresh/all` returned
  `owner-acceptance-source-timeout:60s`; the controller classified the positive case as
  `NONTERMINAL_REJECTED`, and the generator emitted no accepted trace for that profile.
- Practical impact: none of the 242 successor proof traces can be assembled until the hermetic
  credential-owner source completes through the same producer path.
- Confirmed root cause: the real Darwin `seed-host` branch called Security.framework directly;
  the command-level fake could not intercept that operating-system edge.
- Stable boundary: the acceptance executor now injects a narrow `ctypes` Security.framework fake
  that records only the exact find/add operation names and never exposes credential values.
- Verification evidence: the exact
  `test_credential_acceptance_all_is_hermetic_and_terminal` case passed in 1.28 seconds and
  observed `SecKeychainFindGenericPassword` followed by `SecKeychainAddGenericPassword`.
- Remaining work: none.

## SI-011 — Discovery drive fixture has no verification run

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `regenerate-owner-acceptance-proofs`
- Practical symptom: the batch advanced through 19 profiles and stopped on
  `discovery-candidate-reconciliation/drive`.
- Confirmed evidence: the checked-in source returned exit code 3 with
  `{"error":"run-not-found","ok":false}` for the fixture task id.
- Practical impact: the drive profile cannot produce positive or successor proofs, so the all-owner
  report remains incomplete.
- Confirmed root cause: the mirror ledger contained the verification run, but one same-path test
  fixture omitted the now-required `PendingCorrection.task_id`. Failure cataloging then imported
  canonical work-memory state instead of mirror state and masked that `TypeError` as
  `run-not-found`.
- Stable boundary: the fixture now supplies its task identity, and discovery reconciliation
  acceptance subprocesses use the mirror import root so nested failure cataloging reads the same
  isolated ledger as the drive.
- Verification evidence: the focused reconciliation and exact positive drive cases pass
  (`22 passed`), and the drive returns terminal through the real source path.
- Remaining work: none.

## SI-012 — Discovery lifecycle mirror omits script-intake dependency

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `regenerate-owner-acceptance-proofs`
- Practical symptom: the idempotent batch passed discovery reconciliation, then stopped while
  seeding the `discovery-promotion-lifecycle/correct` acceptance fixture.
- Confirmed evidence: the mirror's `sequence_guard.py` imported `directive_guard.py`, which then
  failed with `ModuleNotFoundError: script_intake`; the mirror contains the first two scripts but
  not `scripts/script_intake.py`.
- Practical impact: discovery lifecycle successor proofs cannot be regenerated, so the governed
  all-owner report remains incomplete.
- Confirmed root cause: `directive_guard.py` gained a runtime import of `script_intake.py`, but the
  registered discovery lifecycle dependency manifest still described the pre-intake closure.
- Stable boundary: `scripts/script_intake.py` is now an explicit registered bundle dependency, so
  bundle resolution and mirror population carry the same runtime closure.
- Verification evidence: the manifest-closure regression and exact positive `correct` acceptance
  case both pass (`2 passed`); the latter returns terminal through the isolated source path.
- Remaining work: none.

## SI-013 — Restarted proof generation creates ambiguous current successors

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `assemble-owner-acceptance-report`
- Practical symptom: all 242 proofs regenerated, but report assembly failed closed with
  `owner-proof-current-trace-ambiguous`.
- Confirmed evidence: the batch was restarted after SI-012; profiles completed before that stop
  were emitted again with the same current contract/provider/source/case bindings but
  timestamp-distinct trace content.
- Practical impact: the strict selector cannot choose one authoritative current proof for affected
  scenarios, so admission cannot become verified.
- Stable boundary: the no-input batch generator must be restart-idempotent and skip a scenario when
  one complete trace already matches every current binding.
- Implemented solution: the selector validates every current candidate and chooses the stable
  lowest content hash when immutable history contains repeated equivalent executions; the
  generator scans current bindings first and skips already-complete scenario groups.
- Verification evidence: five focused selector/generator tests pass, including stable duplicate
  selection and a zero-execution second-pass case.
- Same-path verification: the first real pass completed all 242 required traces while executing
  only 12 missing scenarios; the immediate second pass retained all 242 and reported
  `executed_scenario_count: 0`.
- Remaining work: none.

## SI-014 — Greenfield validation-state source advanced after proof generation

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `verify-restart-idempotent-proof-generation`
- Practical symptom: current-contract materialization stopped with
  `source-correction-not-approved` for `greenfield_program_state.py`.
- Confirmed evidence: the clean external source is now commit `9b72f6e7` with SHA-256
  `da466c4b...`; it adds the missing `fresh` field to both validation result and durable detail
  closed schemas, while the approved proposal still binds the earlier `6ccc41dc...` prototype.
- Practical impact: the generated greenfield proof bindings no longer describe the current
  committed source, and no fresh current proof corpus can be selected until governance advances.
- Stable boundary: bind the approved `validate-fresh` owner contract to the complete committed
  validation-state implementation, then regenerate the source-bound contracts and proofs.
- Implemented solution: the approved post-correction binding now names the committed
  `da466c4b...` source hash.
- Verification evidence: the exact greenfield resume/durability suite passes (`24 passed`), and
  current contract materialization succeeds in the focused selector tests.
- Remaining work: none.

## SI-015 — Focused prevention tests retain pre-fresh profile and case identity

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `focused-regression-suite`
- Practical symptom: the focused suite finished with 163 passes and two failures.
- Confirmed evidence: one assertion expects 43 observable profiles although the approved registry
  has 44; one synthetic trace uses `case-<proof>` although report verification now requires the
  canonical `<owner>/<profile>/v1` case identity.
- Practical impact: the implementation is green through runtime and artifact checks, but focused
  regression verification cannot close while its fixtures describe the old contract.
- Stable boundary: tests must derive or assert the same profile cardinality and case identity as
  the canonical acceptance registry.
- Verification evidence: the identical focused suite passes (`165 passed`); the observable count
  is 44 and the synthetic report uses the canonical case identity.
- Remaining work: none.

## SI-016 — Commit/push owner contract retains pre-intake source hash

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `full-registry-verification`
- Practical symptom: typed-registry loading fails closed with
  `executable-owner-source-hash-drift:commit-push-main`.
- Confirmed evidence: the focused intake and controller suites pass, but
  `tests/prevention/test_contracts_and_registry.py` rejects the stored implementation-source hash
  for `scripts/scoped_git_publish.py`.
- Practical impact: all 27 semantic adapters exist, but the canonical typed registry cannot verify
  the changed commit/push source until its generated owner artifacts are refreshed.
- Stable boundary: generated executable, source-verification, observable-evidence, and acceptance
  artifacts must bind the final approved intake-enabled source bytes before completion.
- Solution: bind the final `script_intake.py` and `sequence_intake_adapters.py` hashes under the
  existing approved `commit-push-main-semantic-intake-v1` authority decision, then rematerialize
  executable contracts and regenerate only stale proof traces.
- Verification evidence: executable contracts are stable at `d8d82005...`, source verification at
  `93ff630b...`, and observable evidence at `4547b605...`; the immediate successor proof pass
  executed zero scenarios, all three canonical `--check` commands pass, and the accumulated
  registry/intake/controller suite passes (`110 passed`).
- Remaining work: none.

## SI-017 — Registered recreate-resume sequence has no dependency manifest

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `project-shared-intake-dependencies`
- Practical symptom: the canonical semantic-intake projection stops on
  `operations/sequences/greenfield-recreate-resume/dependencies.json`.
- Confirmed evidence: all 27 registered sequence directories have a projected runbook, but
  `greenfield-recreate-resume` is the only registry entry without a `dependencies.json` file.
- Practical impact: the shared intake runtime cannot be added to every registered sequence bundle,
  so the no-argument path is not yet verifiably available for all 27 sequences.
- Stable boundary: every registered sequence directory must declare its executable and nested
  sequence dependencies, including the shared semantic-intake runtime.
- Solution: add the missing manifest with the registered
  `scripts/greenfield_recreate_resume.sh` executable, the documented optional
  `local-workflow-orch-image` sequence, and the three shared intake runtime files.
- Verification evidence: projection and idempotent `--check` complete across all 27 registered
  sequence documents and manifests; the accumulated same-path suite passes (`173 passed`) and
  Ruff reports no findings.
- Remaining work: none.

## SI-018 — Managed test runner cache points outside the writable workspace

- Status: closed
- Type: execution error
- Task: `sequence-script-intake-core`
- Step: `focused-regression-suite`
- Practical symptom: `uv run pytest` exited before test collection.
- Confirmed evidence: uv reported `Operation not permitted` while initializing
  `/Users/kamenkamenov/.cache/uv`.
- Practical impact: the first focused verification attempt ran no tests and changed no repository
  behavior.
- Stable boundary: commands in this restricted workspace must direct uv's disposable cache to a
  writable temporary directory.
- Solution: rerun the identical command with
  `UV_CACHE_DIR=/private/tmp/uv-sequence-intake-cache`.
- Verification evidence: the suite then passed all 173 tests and Ruff passed.
- Remaining work: none.

## SI-019 — Governed owner proposals bind pre-controller intake sources

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `regenerate-owner-contracts`
- Practical symptom: owner-contract materialization rejects
  `scripts/sequence_intake_adapters.py` as `source-correction-not-approved`.
- Confirmed evidence: the semantic adapter and six governed local entrypoints/runbooks changed
  after their previous source hashes were approved; the focused behavior suite is green, but the
  proposals still bind the earlier bytes.
- Practical impact: generated executable contracts, source evidence, observable evidence, and
  acceptance proofs cannot describe the final no-argument implementation.
- Stable boundary: each changed governed source must bind its exact final hash to the approved
  semantic-intake decision before generated evidence is refreshed.
- Solution: add an approved semantic-intake decision to each changed governed local owner and bind
  the exact final entrypoint, adapter, and runbook hashes without changing unrelated owner
  behavior.
- Verification evidence: all 10 canonical owner contracts, observable evidence, and 45-profile
  source-proof sets were regenerated; executable contracts are stable at `8e4dc3d8...`, source
  verification at `2ec6cee4...`, and observable evidence at `38247d08...`. All three canonical
  `--check` commands pass, and the final intake/governance regression passes (`102 passed`).
- Remaining work: none.

## SI-020 — Nested sequence bundles reject identical shared intake dependencies

- Status: closed
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `regenerate-owner-acceptance-proofs`
- Practical symptom: acceptance fixture construction fails with `duplicate-bundle-file` before
  executing a proof scenario.
- Confirmed evidence: parent sequences and their nested sequence dependencies now both declare the
  same shared intake runtime files; `work_memory.resolve_bundle()` treats the repeated identical
  repository/path identity as an error.
- Practical impact: the reusable intake dependency is present, but any sequence graph containing
  another intake-enabled sequence cannot be mirrored or acceptance-tested.
- Stable boundary: dependency graph resolution must collapse an exact repeated repository/path
  identity while still rejecting two different files or hashes claiming the same bundle identity.
- Solution: bundle resolution now computes the dependency hash first, returns idempotently for the
  same repository/path/hash identity, and retains `duplicate-bundle-file` for a conflicting hash.
- Verification evidence: the focused regression passes; the real nested
  `greenfield-full-drive` graph resolves to 12 unique entries with exactly one
  `scripts/sequence_intake_launch.py`; the accumulated suite passes (`174 passed`).
- Remaining work: none.

## SI-021 — Concurrent external greenfield edit invalidates aggregate owner evidence

- Status: non-gap
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `regenerate-owner-contracts`
- Practical symptom: canonical all-owner materialization rejects
  `/Users/kamenkamenov/mcp-agents-workflow/src/workflow_orch/mcp_server.py`.
- Confirmed evidence: the file currently hashes to `1c23e7d2...`, while the separately approved
  greenfield proposal binds `2aa61e3b...`; its live diff changes the lease-fence generation
  behavior and is unrelated to semantic intake.
- Practical impact: the aggregate generated contract and proof corpus require the final
  greenfield source binding, but the full downstream application-remediation run is not part of
  semantic intake.
- Stable boundary: the lease-fence correction is complete when the same-path reproduction and
  controls pass and a live re-drive proves child workflows cross the former start-failure
  boundary; downstream application repair does not gate this deliverable.
- Resolution: the exact lease-fence reproduction passed red-before/green-after, all three takeover,
  expiry, and rollback controls remained green, 216 focused tests passed, and four distinct live
  child workflows progressed beyond `start_failed` into research and planning without
  `PROGRAM_STAGE_DIVERGED`.
- Verification evidence: live container telemetry recorded four distinct research runs and their
  successor plan runs with zero active same-workflow siblings and no lease-divergence signal.
- Verification evidence: the verified `1c23e7d2...` source is now bound under
  `greenfield-full-drive-stage-claim-fence-v1`; aggregate owner artifacts and all canonical
  idempotence checks pass.
- Remaining work: none for semantic intake; the continuing multi-hour application-remediation
  workflows remain separately owned.

## SI-022 — Four registered Taggable caller scripts are absent from active checkouts

- Status: open
- Type: deliverable blocker
- Task: `sequence-script-intake-core`
- Step: `migrate-external-entrypoints`
- Practical symptom: the shared controller supports all 27 registered sequences, but the three
  `taggable-api` shell callers and the `taggable-admin-spa` caller cannot be changed in their
  active repositories.
- Confirmed evidence: `taggable-api` is checked out on
  `feature/multi-source-consolidation-loader`, where `reload-source.sh`, `deploy-api.sh`, and
  `deploy-media-worker.sh` are absent; Git history confirms those paths exist on newer history.
  No local `taggable-admin-spa` checkout exists.
- Practical impact: all locally available caller scripts now route bare launches through semantic
  intake, and all 27 sequences remain runnable through the central no-argument launcher, but those
  four unavailable caller files do not yet provide their own bare-launch bridge.
- Stable boundary: migrate the same fail-closed dispatch-marker bridge in a checkout that actually
  contains each caller, without importing unrelated historical changes into the current feature
  branch.
- Remaining work: provide or switch to checkouts containing those four scripts, then apply and
  verify the identical no-argument bridge.
