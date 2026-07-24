# Sequence script intake — hardened research result

## Result

The migration boundary is the registered sequence, not a generic command runner. The canonical
registry contains 27 sequences. Every operator-facing sequence must start with no arguments and
collect named domain answers one at a time. The shared intake may validate and retain those
answers, but only a sequence-owned deterministic adapter may create executable names, argv,
flags, JSON objects or files, environment assignments, quoting, escaping, stdin framing, or
shell syntax.

The current prototype is therefore not a stable end state. `scripts/script_intake.py` still has a
generic `argv` question type, and `scripts/sequence_checked_exec.py` exposes it by asking the
operator for an executable and literal argument tokens. Those interfaces preserve the exact
freestyling failure the feature is intended to remove.

Every rendered question must include:

1. one semantic question;
2. the answer format in domain language;
3. one valid example answer;
4. explicit constraints and allowed values;
5. a deterministic validator;
6. no representation of the eventual command structure.

## Universal contract

The shared intake owns question ordering, presentation, validation, conditional branching,
answer persistence, cancellation, resumption, and a final human-readable review. Each registered
sequence owns a versioned adapter with:

- semantic field definitions;
- deterministic transforms from validated answers to typed internal values;
- a fixed executable/subcommand map;
- exact JSON/file/environment/argv serialization;
- redaction rules;
- a no-side-effect preparation result;
- a separate authorization gate before dispatch.

Operator-facing schemas must fail closed if a field requests an executable, subcommand, flag
name, literal argv token, JSON/YAML text, environment assignment, quoted/escaped value, pipe,
redirect, or shell fragment. Free-form human text remains allowed only where the target domain
itself is free text, such as a commit message or task description; the adapter still serializes
it.

## Complete registered-sequence contract inventory

The answer examples below are examples of semantic answers, never command fragments.

### 1. `local-workflow-orch-image`

- Lineage: `local-workflow-orch-image`
- Owner: `mcp-agents-workflow:scripts/local_workflow_orch_image_harness.py`
- Ask: operation (`build`, `recreate`, `seed-auth`, `verify`, or the registered composite);
  repository directory (absolute path, example `/Users/kamenkamenov/mcp-agents-workflow`);
  image/container identity where applicable; whether destructive recreation is approved.
- Derive: the fixed harness executable, registered subcommand, flags, paths, and environment.
- Gate: display the build/recreate/auth manifest before any container, image, or auth effect.

### 2. `greenfield-full-drive`

- Lineage: `greenfield-full-drive`
- Owner: `mcp-agents-workflow:scripts/greenfield_full_drive.sh`
- Ask: new drive or resume; target repository path; specification source; target branch; image
  choice; checkpoint/phase intent; optional DAG choice.
- Example: `new drive`, `/Users/kamenkamenov/project`, `Tasks/feature/spec.md`, `feature/intake`.
- Derive: all controller argv, paths, defaults, environment, and workflow payload files.
- Gate: review before prune/build/recreate/auth seed or workflow dispatch.

### 3. `remote-mcp-user-onboarding`

- Lineage: `remote-mcp-user-onboarding`
- Owners: `dist/remote-mcp-user-admin/remote_mcp_user_admin_tui.py`; internal
  `mawf_get_user`/`mawf_upsert_user` MCP adapters.
- Ask: intended user operation; user identity/profile values; role; activation status; repository
  access choices; confirmation of the displayed current-to-proposed delta.
- Example: `grant repository access`, `kamen@example.com`, `member`, `active`.
- Derive: TUI state and exact MCP request objects. The operator never authors an MCP object.
- Bypasses to remove: documented `--agent-action`; generated next commands; reconstructed retry
  commands; direct public flag mode. Named MCP functions remain internal-only adapters.
- Gate: separate review/apply step for every user, role, status, token, or access mutation.

### 4. `taggable-source-reload`

- Lineage: `taggable-source-reload`
- Owner: `taggable-api:tools/Taggable.MigrationRunner/scripts/reload-source.sh`, present on local
  `origin/main` but absent from the checked-out feature branch.
- Ask: export directory; source-record identity; whether redeployment is needed; requested scale
  behavior; final verification choice.
- Example: `/private/tmp/source-export`, `42`, `redeploy`, `restore original scale`.
- Derive: validated path/id, fixed script flags, Azure job inputs, and restoration manifest.
- Gate: review before blob replacement, scaling, WebJob deployment/trigger, or database load.

### 5. `mawf-playbook-full-test`

- Lineage: `mawf-playbook-full-test`.
- Owners: `mcp-agents-workflow:scripts/mawf_playbook_test_sequence.py` and internal
  `dist/remote-mcp-operator/run.sh`.
- Ask: target repository/project; task description or prompt-file source; workflow start/resume
  intent; semantic gate decisions. The full gate policy is fixed by this registry identity.
- Derive: all discrete driver actions, response files, operator environment, and remote-operator
  request envelopes. `run.sh` is an internal adapter, not a second questionnaire.
- Gate: retain separate approvals for setup, start, gates, continuation, and repair.

### 6. `mawf-playbook-speed-test`

- Lineage: `mawf-playbook-speed-test`.
- Owners: `mcp-agents-workflow:scripts/mawf_playbook_test_sequence.py` and internal
  `dist/remote-mcp-operator/run.sh`.
- Ask: target repository/project; task description or prompt-file source; workflow start/resume
  intent; semantic gate decisions. The speed gate policy is fixed by this registry identity.
- Derive: the speed-policy driver actions, response files, operator environment, and
  remote-operator request envelopes. `run.sh` remains an internal adapter.
- Gate: retain separate approvals for setup, start, gate rejection, continuation, and repair.

### 7. `mawf-playbook-blocker-reentry`

- Lineage: `mawf-playbook-blocker-reentry`
- Owner: non-standalone `record-blocker`/`reenter` actions in
  `scripts/mawf_playbook_test_sequence.py`.
- Ask through the parent session: task identity; blocker evidence; restart scope (`start over`,
  `restart workflow`, or `resume`).
- Derive: the fixed reentry action and evidence payload. Do not create a standalone public CLI.
- Gate: approval for remediation and any widened restart.

### 8. `github-app-repos-refresh`

- Lineage: `github-app-repos-refresh`
- Owners: `mcp-agents-workflow:scripts/github_app_repos_refresh.py`; internal
  `workflow.repos.list`/`workflow.repos.refresh`.
- Ask: target server/profile; actor identity when not derivable; expected repository scope;
  confirmation of the before/after mapping.
- Derive: fixed wrapper invocation and MCP request objects.
- Gate: review target and expected mapping delta before refresh.

### 9. `claude-auth-token-refresh`

- Lineage: `claude-auth-token-refresh`
- Owners: `mcp-agents-workflow:scripts/claude_auth_refresh.sh` and
  `scripts/rotate-credentials.sh`.
- Ask: operation (`status`, `mint`, `seed local`, `seed host`, `push vault`, `reseed Azure`,
  `verify`, or registered composite); non-secret target/profile; credential source reference;
  container/deployment target.
- Derive: fixed command, flags, file references, and secret-store environment. Never ask for or
  persist a secret value in intake answers.
- Gate: review before seed, vault write, remote reseed, or rotation.

### 10. `taggable-api-deploy`

- Lineage: `taggable-api-deploy`
- Owner: `taggable-api:scripts/deploy-api.sh`, present on local `origin/main`.
- Ask: source checkout; target deployment profile (currently the registered development target);
  whether post-deploy verification should run.
- Example: `/Users/kamenkamenov/taggable-api`, `development`, `yes`.
- Derive: fixed script invocation, deployment target, and verification steps.
- Gate: prepare/show deployment manifest, then obtain deploy approval.

### 11. `taggable-admin-spa-deploy`

- Lineage: `taggable-admin-spa-deploy`
- Declared owner: `taggable-admin-spa:scripts/deploy-admin-spa.sh`.
- Current evidence: `/Users/kamenkamenov/FoodCycleScience-admin` is a plausible local SPA
  repository, but the registry-key mapping and declared script ownership are unresolved.
- Planned ask after ownership is proved: source checkout; target profile; semantic API-base
  selection; post-deploy verification.
- Derive: unavailable until the authoritative repository/script is located. No interface may be
  invented from the other deploy scripts.
- Gate: this row blocks complete cross-repository implementation, not the shared intake core.

### 12. `taggable-media-worker-deploy`

- Lineage: `taggable-media-worker-deploy`
- Owner: `taggable-api:scripts/deploy-media-worker.sh`, present on local `origin/main`.
- Ask: source checkout; target deployment profile; post-deploy verification.
- Derive: fixed script invocation and verification steps.
- Gate: prepare/show deployment manifest, then obtain deploy approval.

### 13. `airgapped-local-bulgarian-stt`

- Lineage: `airgapped-local-bulgarian-stt`
- Owners: `callcenter-harness:scripts/setup_airgapped_stt.sh` and
  `scripts/transcribe_airgapped.py`.
- Ask setup: model source/cache destination and whether installation is allowed.
- Ask transcription: input audio path; output destination; language/model choice using named
  values.
- Derive: setup argv/environment and transcription argv/output paths.
- Gate: package/environment mutation requires approval; ordinary bounded transcription does not
  inherit setup authority.

### 14. `airgapped-redaction-stack`

- Lineage: `airgapped-redaction-stack`
- Owners: `callcenter-harness:scripts/setup_airgapped_redaction.sh`,
  `scripts/test_ner_chunk.py`, and the registered redaction smoke path.
- Ask setup: model/cache destination and installation approval.
- Ask smoke: input fixture/path and expected redaction profile.
- Derive: setup/test invocations and deterministic fixture/result paths.
- Gate: package/environment mutation is separate from local smoke execution.

### 15. `callcenter-harness-provision-verify`

- Lineage: `callcenter-harness-provision-verify`
- Owners: composed STT and redaction sequences plus concrete smoke scripts:
  `cc_smoke.py`, `cc_ingest_smoke.py`, `cc_pipeline_smoke.py`, `cc_redact_smoke.py`, and
  `cc_eval_smoke.py`; the large-v3 variant remains a named composed workflow.
- Ask: provision-only, verify-only, or both; fixture/source paths; engine profile; output root;
  whether the large-model variant is required.
- Derive: ordered child manifests and each concrete smoke invocation. No wildcard is an
  executable contract.
- Gate: child setup effects retain their own approvals.

### 16. `airgapped-llm-judge`

- Lineage: `airgapped-llm-judge`
- Owners: `callcenter-harness:scripts/setup_airgapped_judge.sh`,
  `scripts/cc_command_eval_smoke.py`, and internal `scripts/judge_ollama.py`.
- Ask setup/smoke: model/cache destination; fixture; evaluation profile; output destination.
- Derive: setup and smoke argv. `judge_ollama.py` remains a harness-owned stdin-to-JSON machine
  adapter and receives no operator questionnaire.
- Exception proof: its contract is JSON request on stdin and JSON result on stdout; tests must
  prove it is reachable only through the named harness consumer and cannot become a public
  argument bypass.

### 17. `secure-landing-seed`

- Lineage: `secure-landing-seed`
- Owners: `callcenter-harness:scripts/seed_landing.sh` and
  `scripts/scrub_and_retire.py`.
- Ask: source input path; landing target; tenant/batch identity; retention/retirement intent;
  dry-run versus approved apply.
- Derive: safe path validation, fixed argv, and a file manifest.
- Gate: seed and retirement are separate effect authorizations; destructive retirement shows an
  exact manifest first.

### 18. `callcenter-harness-engine-invariants`

- Lineage: `callcenter-harness-engine-invariants`
- Owner: parameterless `callcenter-harness:scripts/test_engine_upgrades.py`; optional real smoke
  uses `scripts/cc_redact_smoke.py`.
- Exception: the pure invariant test needs no intake because it accepts no operator parameters.
- Ask only for optional real smoke: fixture/path, engine profile, and output root.
- Derive: the optional smoke invocation without changing the pure test contract.

### 19. `discovery-promotion-lifecycle`

- Lineage: `discovery-b6658d35-7870-5d15-9f4b-d316138cec83`
- Owner: `memory-knowledge:scripts/discovery_promotion_lifecycle.py`.
- Ask: lifecycle operation; discovery/sequence identity; repository references; correction or
  successor semantics where applicable.
- Derive: fixed subcommand, validated identities, dependency/repository JSON files, and paths.
- Gate: review before registry or durable sequence mutation.

### 20. `commit-push-main`

- Lineage: `discovery-9c51594b-6ca3-54a0-b7d7-31632ac2d48c`
- Owner: `memory-knowledge:scripts/scoped_git_publish.py`.
- Ask: operation from the six registered semantic modes (`dry run`, `publish`, `resume push`,
  `integrate remote and resume`, `isolated integrate and resume`, `isolated reconcile and
  resume`); repository path; exact approved file paths; commit message where needed; branch and
  remote choices; resume commit where needed; overlay/ledger/view choices only for the applicable
  reconciliation mode.
- Example: `dry run`; `/Users/kamenkamenov/memory-knowledge`; approved files
  `scripts/script_intake.py` and `tests/test_script_intake.py`; message
  `Add deterministic sequence intake`.
- Derive: the scoped manifest file and every fixed CLI argument. The operator never writes the
  manifest JSON or quotes a path.
- Gate: dry-run/review first; commit and push remain separately authorized operations.

### 21. `discovery-bootstrap`

- Lineage: `discovery-1cd9d4cf-c214-58b4-b5a7-022f51a2d344`
- Owner: `memory-knowledge:scripts/discovery_bootstrap.py`.
- Ask: discovery purpose; required/optional dependency identities; repositories; output
  destination; activation intent.
- Derive: exact specification/dependency/repository files and controller invocation.
- Gate: review before durable discovery creation/activation.

### 22. `discovery-candidate-reconciliation`

- Lineage: `discovery-782832ed-7fa4-5efe-9765-463303ecd2a2`
- Owner: `memory-knowledge:scripts/discovery_candidate_reconciliation.py`.
- Ask: reconciliation operation; candidate/successor identity; relationship and correction
  reasons; evidence references.
- Derive: fixed subcommand and typed reconciliation payload.
- Gate: review before durable lifecycle mutation.

### 23. `convergence-checkpoint-run`

- Lineage: `discovery-240e46ff-483d-51e7-94cc-3adb208506d2`
- Owner: `memory-knowledge:scripts/convergence_checkpoint_run.py`.
- Ask: state path; repository path; approval identity; child purpose; child prompt/skill names as
  semantic values; stage; optional prevention evidence identity.
- Derive: the `child-intent` JSON file/object and fixed current `--child-intent-json` interface.
  The materialized owner metadata currently claiming `--command-json` is stale and must be
  corrected from source, not implemented.
- Gate: checkpoint approval remains distinct from child-command construction.

### 24. `scoped-context-edit`

- Lineage: `discovery-1c6cdb98-3710-5220-895a-11ae9a2822c8`
- Owner: the scoped-context controller’s `prepare`, `check`, `verify`, `cancel`, and `self-check`
  operations; source ownership must be bound to the registered implementation during planning.
- Ask: semantic operation; target context; approved files; intended edit purpose; verification
  evidence; cancellation reason when applicable.
- Derive: fixed operation and typed state payload.
- Gate: preparation does not authorize editing; verification/cancellation retain state guards.

### 25. `convergence-state-review-cycle`

- Lineage: `discovery-5771be28-92af-5f65-ac15-546114a90d01`
- Owner: `memory-knowledge:scripts/convergence_state_review_cycle.py`.
- Ask: state path; review scope; reviewer intent; evidence sources; disposition.
- Derive: request JSON and fixed controller invocation.
- Gate: review output cannot silently authorize follow-on mutation.

### 26. `greenfield-recreate-resume`

- Lineage: `greenfield-recreate-resume`
- Owner: `mcp-agents-workflow:scripts/greenfield_recreate_resume.sh`.
- Ask: repository/project identity; resume task/run identity; image and auth profile; checkpoint
  source; verification intent.
- Derive: all shell argv/environment and resume payload.
- Gate: review before recreation, auth seed, or resume dispatch.
- Evidence limitation: the registered sequence bundle currently lacks `dependencies.json`.

### 27. `workflow-resume-from-phase-live-confirmation`

- Lineage: `discovery-9c0393de-2d1b-5744-8e85-2f519d56edea`
- Owners: `united-partners:scripts/run_client_regeneration.py`,
  `scripts/codex_role_command.py`, and `scripts/watch_run.py`.
- Ask: client/workflow identity; phase to resume from; repository/project target; run/task
  identity; role intent; monitoring duration/terminal condition.
- Derive: environment, driver command, role request, and watcher invocation.
- Gate: live workflow resume requires explicit approval; monitoring does not broaden it.

## Authoritative bypass classes and required dispositions

1. `operations/sequences/SEQUENCES.md`: remove direct flag templates as operator instructions;
   point each row to its no-argument controller.
2. Every registered `operations/sequences/*/sequence.md`: replace direct argv, environment, JSON,
   and multi-command construction with semantic launch-and-answer instructions.
3. Source and installed `skills/sequence-runner/SKILL.md`: stop teaching the complete
   `sequence_checked_exec.py` envelope; invoke the registered no-argument controller.
4. `remote_mcp_user_admin_tui.py`: remove public agent-action flag guidance and argument-bearing
   generated/retry commands; preserve named MCP calls behind the controller.
5. Legacy argument-bearing script CLIs: allow only enumerated machine consumers. Unsupported
   direct operator use must fail closed or route to intake; compatibility must have tests.
6. Generated “next command” strings, wrappers, help text, tests, and copied installed skills are
   migration surfaces, not documentation-only cleanup.

## Repository handoff

- `memory-knowledge`: shared intake contract; schema prohibition checks; sequence adapter
  registry; six local controllers; registry/docs/source-and-installed skill migration; unit and
  static bypass tests.
- `mcp-agents-workflow`: image, greenfield, MAWF, GitHub refresh, credential, and user-admin
  adapters; generated-command removal; internal MCP/remote-operator compatibility tests.
- `taggable-api`: acquire the authoritative `origin/main` implementations into the intended
  implementation branch, then add source-reload/API/media deploy adapters and dry-run tests.
- `taggable-admin-spa`: resolve repository-key and script ownership before planning its code
  change. Do not infer it from `FoodCycleScience-admin`.
- `callcenter-harness`: setup/smoke/seed/cleanup adapters; preserve the judge machine adapter and
  parameterless invariant-test exceptions with explicit tests.
- `united-partners`: one session adapter across regeneration, role command, and watcher.

Safe verification is static parsing, no-argument prompt snapshots, validator/transform unit
tests, golden derived-payload tests, forbidden-schema tests, caller/bypass searches, help
contract tests, and dry-run/manifest tests. Live build, container, auth, database, deployment,
push, cleanup, and workflow-drive verification remain separately approval-gated.

## Planner-ready acceptance boundary

Implementation is complete only when:

- all 27 registry identities have an adapter or an explicit proved exception;
- every concrete executable and named internal adapter has a caller boundary;
- no operator-facing schema accepts invocation syntax;
- every question renders format, example, and constraints;
- golden tests prove semantic answers produce exact internal payloads;
- normal no-argument launch is side-effect free until review/authorization;
- every authoritative direct-command bypass is migrated or explicitly contained;
- commit, push, and deploy operations remain separate approval gates;
- the unresolved admin-SPA owner is resolved rather than guessed.
