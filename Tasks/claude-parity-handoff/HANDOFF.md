# Claude parity handoff

Status: implementation handoff; no implementation authorization is implied by this document.

Intended implementer: Claude Code, operating in this repository and driving its own upgrade through the canonical `prototype-driven-implementation` controller.

Repository: `/Users/kamenkamenov/memory-knowledge`

Directive authority: `working-agreement/DIRECTIVES.md`, reviewed at revision 2026-07-23.

## 1. Outcome

Bring Claude Code to behavioral parity with the current Codex working system without creating a second hand-maintained workflow architecture.

When this work is complete:

1. Claude receives the same current directives and selects the same task mode as Codex.
2. Every managed skill is either installed identically in both clients or produced from one canonical source through an explicit, validated client projection.
3. `prototype-driven-implementation` is Claude's central controller for all implementation work. Research, planning, write-code, and review playbooks remain supporting projections selected by observed prototype gaps.
4. Claude uses the same zero-input sequence intake, sequence registry, promotion plumbing, work-memory lifecycle, and blocker-resolution lifecycle as Codex.
5. Host-specific agent execution and thread identity are isolated behind explicit adapters. Shared contracts do not assume that every host is Codex.
6. Old Claude commands cannot bypass the current directives, prototype controller, approval boundaries, sequence intake, or verification contracts.
7. A deterministic parity check detects a missing, stale, divergent, or incorrectly projected Claude capability before installation is reported successful.

This is behavioral parity, not textual sameness. Byte-for-byte installation is preferred where the canonical skill already works on both clients. A generated Claude projection is allowed only where the host surface genuinely differs.

## 2. Non-goals and approval boundaries

The following are not authorized merely by this handoff:

- writing to `~/.claude`, `~/.codex`, or another global client directory;
- committing or pushing;
- changing another repository;
- deployment, authentication, credentials, external messages, or destructive cleanup;
- redesigning the playbooks or sequence system beyond changes required for Claude parity;
- replacing shared deterministic intake with Claude-specific prompt logic.

Claude must first freeze a `prototype-driven-implementation` autonomy envelope and obtain Kamen's approval. The envelope should allow this repository and the exact paths named in this handoff. Global installation into `~/.claude` must remain a separate, explicit approval and should happen only after repository-local verification passes.

## 3. Grounded current state

### 3.1 What already works

| Capability | Current evidence | Assessment |
| --- | --- | --- |
| Directive authority | `working-agreement/DIRECTIVES.md` | Canonical and current. |
| Claude directive delivery | `working-agreement/inject-directives.sh`; the configured `UserPromptSubmit` hook in `~/.claude/settings.json` | Present. Preserve and verify; do not replace the settings file. |
| Claude corpus/repo-memory delivery | Existing `UserPromptSubmit` hooks for corpus and repo memory | Present. Outside the parity defect unless verification proves otherwise. |
| Claude closeout capture | Existing `Stop` hook for auto-capture | Present. Preserve. |
| Managed-skill authority | `skills/managed-skills.txt` | Present; 31 entries including `_shared`. |
| Transactional installer | `working-agreement/install_skills.py` | Present; locks, journals, recovers, exact-replaces managed directories, and verifies tree hashes. |
| Tracked refresh hook | `.githooks/post-merge`, `working-agreement/install-skills.sh` | Present but not operational for parity: this checkout has no active `core.hooksPath`, and the wrapper currently invokes the installer through its Codex-only default. |
| Canonical prototype controller | `skills/prototype-driven-implementation/` | Present for Codex; missing from installed Claude skills. |
| Prototype support projections | `skills/prototype-driven-implementation/support-projections.json` and `scripts/generate_support_projections.py` | Present and source-hash bound. |
| Sequence registry | `operations/sequences/SEQUENCES.md` | Canonical shared registry. |
| Deterministic semantic intake | `scripts/script_intake.py`, `scripts/sequence_intake_adapters.py`, `scripts/sequence_intake_launch.py` | Present. The launch boundary deliberately accepts no arguments. |
| Sequence promotion/doc checks | Sequence registry, semantic-intake markers, adapters, and related tests | Present for Codex workflow; Claude's installed sequence skill is stale. |
| Work memory | `scripts/work_memory.py`, `scripts/sequence_guard.py`, `operations/work-memory/events.jsonl` | Present, but thread identity still has a Codex-specific assumption. |
| Blocker lifecycle | `scripts/blocker_catalog.py`, `operations/blockers/BLOCKERS.md`, `skills/blocker-catalog/` | Present; installed Claude skill is stale. |

Claude Code 2.1.126 is installed locally. Its real CLI help confirms bounded non-interactive execution with `claude -p`, structured `json` or `stream-json` output, tool allow/deny lists, `--max-budget-usd`, `--permission-mode`, `--max-turns`, `--session-id`, custom agents, and settings-source controls. The implementation must derive its invocation from the installed CLI help and cover it with a capability probe instead of assuming Codex flags. The public CLI reference also documents print mode, structured output, turn limits, permissions, and resume behavior: <https://docs.anthropic.com/en/docs/claude-code/cli-usage>.

### 3.2 Confirmed parity defects

#### Installed skills

The installed Claude skill set is not at current canonical parity.

- Missing from Claude: `prototype-driven-implementation`.
- Extra unmanaged legacy skill: `code-quality-review-loop`.
- Canonical match at inventory time:
  - `auto-capture`
  - `corpus-add`
  - `critic-foundry`
  - `doc-gap-closure-loop`
  - `phase-categorization-foundry`
  - `phase-ledger-category-contract-foundry`
  - `phase-ledger-contract-hardener`
  - `producer-foundry`
  - `remote-mcp-operator`
  - `remote-mcp-user-admin`
  - `requirements-coverage-gap-loop`
  - `requirements-satisfaction-gap-loop`
  - `reproduce-first-verify`
  - `review-playbook`
  - `shell-canary-foundry`
  - `verifier-foundry`
  - `verify-analysis`
  - `verify-work`
- Canonical tree drift at inventory time:
  - `_shared`
  - `blocker-catalog`
  - `plan-playbook`
  - `playbook-convergence-loop`
  - `research-playbook`
  - `sequence-runner`
  - `shell-canary-runner`
  - `task-intake`
  - `task-workflow`
  - `verify-plan`
  - `working-agreement`
  - `write-code-playbook`

This inventory is evidence of the present defect, not a permanent expected list. The final parity checker must calculate the set and hashes on every run.

#### Routing and lifecycle

The installed Claude `working-agreement` view is stale: it routes implementation through `write-code-playbook` and does not encode the current fast-path/governed-path distinction. The canonical route is:

- ordinary read-only local work: direct mode-specific work;
- write-code work: `prototype-driven-implementation` as central controller;
- research, plan, write-code, and review: bounded supporting projections pulled only when observed evidence requires them;
- governed operational work: `sequence-runner` before operational commands.

#### Sequence intake

The installed Claude `sequence-runner` still describes manual discovery and guard invocation. The current canonical behavior is:

1. Claude launches `python3 scripts/sequence_intake_launch.py` with no arguments.
2. The intake asks one semantic question at a time.
3. Every question states the required answer format, constraints, and an example.
4. Claude answers only the semantic question.
5. Deterministic code derives the JSON envelope, file paths, environment, flags, and final argv.
6. The exact operation is shown for authorization.
7. The controller dispatches through the guard.

Claude must not construct the sequence JSON envelope or freestyle the script parameters.

#### Installer reconciliation

`working-agreement/install_skills.py` protects `--target both` with cross-client reconciliation, but direct `--target claude` does not require equivalent reconciliation. The current reconciliation check also recognizes only one unresolved status, `claude-divergent-preserved`; it does not prove a complete one-to-one decision for every managed skill.

Practical consequence: a caller can install canonical bytes into Claude without proving they are valid for Claude, or can preserve stale Claude variants without a complete reasoned manifest.

The maintenance path is also incomplete. A tracked `.githooks/post-merge` exists, but the checkout does not currently activate it through `core.hooksPath`; if activated as written, its wrapper still invokes the default Codex target. Therefore a pull cannot currently be claimed to refresh Claude.

#### Codex-specific runtime assumptions

The shared workflow is not fully client-neutral:

- `scripts/work_memory.py` uses `CODEX_THREAD_ID` as its host-thread identity.
- `skills/research-playbook/scripts/research_run.py` constructs `codex exec` invocations.
- several helpers or skill references point directly at `~/.codex/skills`.
- some canary tooling intentionally targets Codex. Those references may be domain-correct and must not be replaced blindly.

Every occurrence must be classified as one of:

1. host orchestration assumption that must become client-neutral;
2. intentionally Codex-targeted behavior that remains unchanged;
3. documentation/example that must describe both hosts;
4. legacy path to retire.

The initial occurrence inventory and locked disposition are:

| Surface | Classification | Required action |
| --- | --- | --- |
| `scripts/work_memory.py: HOST_THREAD_ENV` | Host orchestration leak | Replace the universal Codex environment assumption with the versioned host/session identity contract; retain legacy read compatibility. |
| `skills/research-playbook/scripts/research_run.py` Codex executable/argv | Host orchestration leak | Route through `skills/_shared/host_agent_runtime.py`; retain a Codex adapter and add a Claude adapter. |
| `skills/reproduce-first-verify/SKILL.md` Codex ledger path and `close_agent` | Host orchestration leak | Refer to the shared ledger and host-accurate lifecycle contract. |
| `skills/playbook-convergence-loop/SKILL.md` and its plan-playbook integration projection | Host orchestration leak | Replace unconditional `close_agent` with host-accurate terminal/release semantics and regenerate the integration projection from its authority. |
| `skills/phase-ledger-category-contract-foundry/SKILL.md` absolute Codex helper path | Host path leak | Resolve the helper from the active installed skill root or canonical repository root. |
| `skills/phase-ledger-contract-hardener/SKILL.md` absolute Codex helper path | Host path leak | Resolve the helper from the active installed skill root or canonical repository root. |
| `scripts/convergence_state_review_cycle.py` Codex helper default | Host path leak | Resolve through an explicit `--helper`/client-root contract with repository fallback; no hard-coded client default. |
| `scripts/convergence_checkpoint_run.py` Codex helper default | Host path leak | Use the same helper-resolution contract as the review cycle. |
| `scripts/promote_plan_playbook.py` trusted Codex install root | Cross-client promotion gap | Promotion must verify both approved installed client projections; repository promotion remains one canonical operation. |
| `scripts/prevention_owner_acceptance_fixtures.py` `CODEX_THREAD_ID` | Host-neutral acceptance gap | Add client-kind/session fixtures and retain a legacy Codex case. |
| `scripts/prevention_owner_acceptance_producer.py` `CODEX_THREAD_ID` | Host-neutral acceptance gap | Produce the versioned client identity environment; keep literal `codex exec` branches that intentionally simulate Codex sequence behavior. |
| `scripts/prevention_owner_acceptance_producer.py` literal `codex exec` cases | Intentionally Codex-targeted domain behavior | Keep; add separate Claude host-adapter acceptance rather than renaming the simulated command. |
| `working-agreement/install_skills.py` `.codex/skills` and `.claude/skills` roots | Intentional client installation behavior | Keep both explicit roots; place reconciliation/projection validation before either client mutation. |
| `working-agreement/SETUP-autocapture.md` Codex-only example | Documentation gap | Document both clients and shared hook behavior. |
| Shell canary skills and `probe-codex` sequence steps | Intentionally Codex-targeted canary behavior | Keep when the system under test is Codex; parity requires Claude to operate the sequence, not rename its target. |

Before editing, Claude must rerun the focused search for `CODEX_THREAD_ID`, `codex exec`, `.codex/skills`, and `close_agent`. A newly discovered occurrence is read-only evidence; editing it requires adding its exact path to the approved allowlist.

#### Legacy Claude commands

Repository-local `.claude/commands/review-fix-loop.md`, `.claude/commands/verify-analysis.md`, and `.claude/commands/verify-plan.md` encode older lifecycle behavior. They include such conflicts as automatic commits, direct test invocation, or autonomous fix loops that are no longer the authoritative controller.

Practical consequence: Claude can enter through a legacy command and bypass PDI, current approval boundaries, generated plan/research contracts, or sequence governance.

#### Verification baseline

The canonical skill and PDI projection checks pass, but the inspected focused parity-related baseline is not entirely green: 107 tests passed and 2 work-memory contract-probe cases failed with `task-writer-not-owner`. The probe isolates receipts but reuses fixed `probe-*` task IDs against the shared ownership ledger, so old state can collide with a later probe run.

This is a pre-existing verification defect. Claude must isolate or uniquely namespace the probe state before using it as parity evidence; it must not attribute the failures to its new implementation or report a clean baseline.

## 4. Locked target architecture

### 4.1 One authority, three layers

The architecture must have these layers:

1. **Canonical semantic layer**
   - `working-agreement/DIRECTIVES.md`
   - `skills/<managed-skill>/`
   - playbook contracts and PDI support projections
   - sequence registry, intake specifications, work-memory, and blocker contracts

2. **Client projection layer**
   - deterministic projection metadata;
   - generated Codex or Claude artifacts only where the host interface differs;
   - source hashes binding every projection to canonical inputs;
   - no manually edited installed variants.

3. **Installed/runtime layer**
   - transactional installation;
   - host capability probing;
   - hash and behavior verification;
   - explicit global-install approval.

The installed client directories are outputs, never authorities.

### 4.2 Projection rule

Each managed skill must have exactly one parity disposition:

- `SHARED_IDENTICAL`: install canonical bytes unchanged in both clients.
- `GENERATED_CLIENT_PROJECTION`: generate client bytes from canonical files plus a declared, hash-bound transformer.
- `CLIENT_NOT_APPLICABLE`: allowed only with an evidence-backed reason and an acceptance test proving the capability is supplied elsewhere.
- `BLOCKED`: no installation until the missing host capability or design decision is resolved.

“Preserve whatever Claude currently has” is not a terminal parity disposition.

Projection metadata must record at least:

- managed skill name;
- canonical source tree hash;
- disposition;
- target client;
- generator/transformer identity and hash when generated;
- projected tree hash;
- reason for divergence;
- verification scenario IDs.

The projection build must be deterministic: the same canonical tree and projection metadata produce the same output tree.

### 4.3 Runtime adapter rule

Host differences belong behind a small runtime boundary, not scattered through playbooks.

The adapter contract covers assessment-only research, plan, review, verifier, critic, and audit roles. It does not perform write-code support: the parent PDI controller is the sole authorized state writer and consumes the write-code support projection directly.

For assessment roles, the adapter contract must cover:

- host identity: `codex` or `claude`;
- current session/thread identity;
- launching a bounded assessment-only agent;
- binding the runtime agent ID to `skills/_shared/agent_slot_ledger.py`;
- collecting structured terminal output;
- detecting success, failure, timeout, and cancellation;
- recording completion evidence;
- releasing the slot;
- resuming only when the host supports the required semantics.

Do not invent a Claude “close agent” operation if the client has no such operation. Model the actual completion boundary and prove that the shared ledger reaches zero active slots.

The adapter interface is locked as follows:

- module: `skills/_shared/host_agent_runtime.py`;
- `probe_host(executable: str, host: str) -> HostCapabilities`;
- `run_assessment(request: HostAgentRequest, ledger_path: Path) -> HostAgentResult`.

`HostAgentRequest` contains exactly:

- `schema_version: Literal[1]`;
- `host: Literal["codex", "claude"]`;
- `executable: str`, an absolute executable path;
- `role: str`, non-empty;
- `prompt_path: Path`, an absolute regular file;
- `working_directory: Path`, an absolute directory;
- `allowed_read_roots: tuple[Path, ...]`, non-empty absolute directories;
- `allowed_tools: tuple[str, ...]`;
- `disallowed_tools: tuple[str, ...]`;
- `timeout_seconds: int`, positive;
- `max_turns: int`, positive;
- `max_budget_usd: Decimal`, positive;
- `output_schema: dict[str, object]`, a valid JSON Schema object;
- `slot_id: str`, non-empty;
- `attempt_id: str`, non-empty.

`HostCapabilities` contains exactly:

- `schema_version: Literal[1]`;
- `host: Literal["codex", "claude"]`;
- `executable: str`, absolute;
- `version: str`;
- `help_sha256: str`, 64 lowercase hexadecimal characters;
- `supported_flags: tuple[str, ...]`;
- `missing_required_flags: tuple[str, ...]`;
- `available: bool`, true exactly when the executable works and no required flag is missing.

`HostAgentResult` contains exactly:

- `schema_version: Literal[1]`;
- `host: Literal["codex", "claude"]`;
- `role: str`;
- `attempt_id: str`;
- `slot_id: str`;
- `runtime_agent_id: str | None`, null before a host runtime identity exists;
- `session_id: str | None`, null when the host never emitted one;
- `status: Literal["SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "CAPABILITY_MISSING", "INVALID_OUTPUT", "LEDGER_ERROR"]`;
- `exit_code: int | None`, null when no process terminal code exists;
- `started_at_utc: str`, RFC 3339 UTC;
- `completed_at_utc: str`, RFC 3339 UTC;
- `output: dict[str, object] | None`, null unless schema-valid structured output exists;
- `output_sha256: str | None`, null exactly when output is null;
- `diagnostic_code: str | None`, null only for `SUCCEEDED`;
- `completion_evidence: CompletionEvidence`;
- `slot_released: bool`.

`CompletionEvidence` contains exactly five booleans: `process_terminal`, `host_terminal`, `ledger_completed`, `ledger_closed`, and `ledger_released`.

Terminal precedence is locked:

1. failed capability probe or missing required flag -> `CAPABILITY_MISSING`, no process/agent/session/exit code;
2. caller cancellation -> `CANCELLED`;
3. elapsed timeout -> `TIMED_OUT`;
4. nonzero process exit or host error result -> `FAILED`;
5. zero process exit with absent, malformed, or schema-invalid structured output -> `INVALID_OUTPUT`;
6. any completion, closure, or release failure -> `LEDGER_ERROR`, even if model output was valid;
7. only valid structured output plus successful required ledger transitions -> `SUCCEEDED`.

Every launched terminal path attempts ledger completion, host-accurate closure, and release in `finally`. A never-launched capability failure has all five completion-evidence fields false and `slot_released=false`; the caller must not acquire a slot before capability probing.

### 4.4 Shared deterministic intake rule

Claude and Codex must call the same `scripts/sequence_intake_launch.py`. There must not be a Claude-specific copy of:

- semantic questions;
- answer schemas;
- example text;
- parameter derivation;
- JSON-envelope construction;
- argv construction;
- guard dispatch.

Client projection may change only the instruction that tells the host how to launch and answer the shared intake.

## 5. Bootstrap: how Claude takes control of its own upgrade

Claude currently lacks the installed PDI skill, so bootstrap must be explicit and bounded.

### Bootstrap 0 — read authority without installing

Claude starts in this repository and reads:

- `working-agreement/DIRECTIVES.md`;
- `skills/working-agreement/SKILL.md`;
- `skills/prototype-driven-implementation/SKILL.md`;
- `skills/prototype-driven-implementation/support-projections.json`;
- the PDI references and generator named by that skill;
- this handoff.

Reading the canonical PDI from the repository is a temporary bootstrap, not an installed parity claim.

### Bootstrap 1 — freeze the autonomy envelope

Claude proposes one PDI envelope containing:

- outcome: the terminal behavior in section 1;
- repository: only `memory-knowledge`;
- allowed paths: the files and directories in section 6;
- exclusions: section 2;
- real cases: section 7;
- attempt/time bounds;
- no global installation, commit, push, deployment, credential access, or destructive cleanup.

Claude waits for explicit approval before repository edits.

The initial repository write allowlist is exact:

- `.claude/commands/review-fix-loop.md`
- `.claude/commands/verify-analysis.md`
- `.claude/commands/verify-plan.md`
- `.githooks/post-merge`
- `operations/sequences/sequence-intake-contracts.json` (`CREATE`)
- `scripts/convergence_checkpoint_run.py`
- `scripts/convergence_state_review_cycle.py`
- `scripts/prevention_owner_acceptance_fixtures.py`
- `scripts/prevention_owner_acceptance_producer.py`
- `scripts/promote_plan_playbook.py`
- `scripts/sequence_guard.py`
- `scripts/sequence_intake_adapters.py`
- `scripts/sequence_intake_launch.py`
- `scripts/work_memory.py`
- `scripts/work_memory_contract_probe.py`
- `skills/_shared/host_agent_runtime.py` (`CREATE`)
- `skills/phase-ledger-category-contract-foundry/SKILL.md`
- `skills/phase-ledger-contract-hardener/SKILL.md`
- `skills/plan-playbook/integration/playbook-convergence-loop.SKILL.md`
- `skills/playbook-convergence-loop/SKILL.md`
- `skills/prototype-driven-implementation/**`
- `skills/reproduce-first-verify/SKILL.md`
- `skills/research-playbook/scripts/research_run.py`
- `skills/sequence-runner/SKILL.md`
- `skills/working-agreement/SKILL.md`
- `working-agreement/SETUP-autocapture.md`
- `working-agreement/SETUP-claude.md`
- `working-agreement/SETUP-codex.md`
- `working-agreement/client-skill-projections.json` (`CREATE`)
- `working-agreement/install-skills.sh`
- `working-agreement/install_skills.py`
- `working-agreement/project_client_skills.py` (`CREATE`)
- `working-agreement/validate-skills.sh`
- `working-agreement/validate_skills.py`
- `tests/test_claude_parity.py` (`CREATE`)
- `tests/test_client_skill_projections.py` (`CREATE`)
- `tests/test_active_discovery_recovery_v1.py`
- `tests/test_correction_preservation.py`
- `tests/test_host_agent_runtime.py` (`CREATE`)
- `tests/test_prototype_support_projections.py`
- `tests/test_script_intake.py`
- `tests/test_sequence_intake_adapters.py`
- `tests/test_sequence_intake_doc_projection.py`
- `tests/test_sequence_intake_launch.py`
- `tests/test_sequence_guard.py`
- `tests/test_work_memory.py`
- `tests/test_work_memory_bootstrap.py`
- `tests/test_work_memory_contract_probe.py`

Reading other repository files is allowed for grounding. Editing a path not listed above requires a scope-expansion stop and new approval. A prototype may narrow this allowlist but may not widen it silently.

### Bootstrap 2 — Prototype 0

Prototype 0 must run the current system through one cheap, real path and preserve the failure:

1. calculate canonical-versus-Claude managed skill inventory;
2. demonstrate that PDI is missing or stale at the installed Claude root;
3. run a dry projection/install validation without modifying the installed root;
4. attempt one Claude-hosted parity scenario that exposes a real current gap, preferably zero-input sequence intake routing or PDI task routing;
5. capture the exact observable.

Do not begin with a synthetic full rewrite.

### Bootstrap 3 — adaptive implementation

Each subsequent prototype closes the next observed blocking gap. Promote, revise, or discard it based on the real acceptance scenarios. Pull research or planning support only when an observed uncertainty requires it.

### Bootstrap 4 — install last

After repository-local parity tests pass:

1. generate the exact Claude install manifest and before/after hash report;
2. request separate approval to modify `~/.claude`;
3. install transactionally;
4. open a fresh Claude session;
5. execute the same real parity scenarios against the installed surface;
6. roll back from the install journal if post-install verification fails.

## 6. Implementation workstreams

The file placement and contracts below are locked. If Prototype 0 proves an anchor invalid, Claude stops with the evidence and requests a revised path authorization.

### Workstream A — parity inventory, projection contract, and installer

#### Existing files to modify

- `working-agreement/install_skills.py`
- `working-agreement/validate_skills.py`
- `working-agreement/install-skills.sh`
- `working-agreement/validate-skills.sh`

#### Verify only

- `skills/managed-skills.txt`; if it is incomplete, stop for scope expansion rather than editing it under this handoff.

#### Files to create

- `working-agreement/client-skill-projections.json` — repository-owned client-projection manifest;
- `working-agreement/project_client_skills.py` — deterministic projection builder/checker;
- focused tests for the projection and installation contracts.

#### Required behavior

1. Inventory every manifest-managed skill for both clients.
2. Fail if a managed skill lacks a parity disposition.
3. Bind dispositions and generated outputs to source hashes.
4. Generate into a temporary/staging root, never directly into the installed root.
5. Run canonical skill validation and client-projection validation before installation.
6. Require reconciliation for every Claude-targeting mutation, including `--target claude`.
7. Preserve unrelated/unmanaged installed skills, but report them explicitly.
8. Exact-replace only selected managed destinations.
9. Retain the existing lock, journal, recovery, fsync, and post-install tree-hash behavior.
10. Produce a machine-readable and human-readable parity report.
11. Refuse installation when canonical inputs changed after projection.

#### Before and after

- Before: Claude can be stale, missing PDI, or divergent while the installer still has an invocation that can write to Claude.
- After: every Claude-targeted install is backed by a complete, current, deterministic reconciliation and fails closed on drift.

### Workstream B — make PDI the Claude implementation controller

#### Existing files to modify

- `skills/prototype-driven-implementation/**`
- `skills/working-agreement/SKILL.md`
- `skills/playbook-convergence-loop/SKILL.md`
- `skills/plan-playbook/integration/playbook-convergence-loop.SKILL.md`
- `tests/test_prototype_support_projections.py`

#### Verify only

- `skills/write-code-playbook/SKILL.md`
- `skills/research-playbook/**` except the separately authorized `scripts/research_run.py`
- `skills/plan-playbook/**` except the integration file above
- `skills/review-playbook/**`

A failed verify-only check stops for scope expansion.

#### Required behavior

1. Install or project PDI for Claude.
2. A Claude write-code task routes to PDI, not directly to the write-code playbook.
3. PDI starts on a real code path with a frozen autonomy envelope.
4. PDI pulls the generated research/plan/write-code/review support projection only after a concrete gap requires it.
5. Source-hash drift in any supporting playbook makes projection verification fail closed.
6. Commit, deployment, global install, credentials, destructive work, another repository, and external messages remain stop boundaries.
7. Claude discovers PDI from the shared `SKILL.md`; `agents/openai.yaml` is inert extra metadata on Claude and is not required for discovery. If the capability probe disproves this, mark the PDI row `BLOCKED` and request a revised projection design/approval; do not generate an unapproved client variant.

#### Before and after

- Before: Claude can route implementation through stale write-code instructions and never enter the prototype controller.
- After: the same task on Claude and Codex enters the same PDI lifecycle and differs only in host-native execution mechanics.

### Workstream C — host-neutral agent execution

#### Existing files to modify

- `skills/research-playbook/scripts/research_run.py`
- `skills/playbook-convergence-loop/SKILL.md`
- `skills/plan-playbook/integration/playbook-convergence-loop.SKILL.md`
- `tests/test_host_agent_runtime.py` (`CREATE`)
- `tests/test_claude_parity.py` (`CREATE`)

#### Verify only

- `skills/_shared/agent_slot_ledger.py`; the adapter uses its existing public lifecycle. If the existing ledger cannot represent the locked runtime result, stop for scope expansion.

#### File to create

- `skills/_shared/host_agent_runtime.py` — the small shared host-agent adapter module.

#### Required Claude execution contract

Use capabilities proven by the installed `claude --help`, not guessed flags. The current host supports:

- `claude -p`;
- `--output-format json|stream-json`;
- `--json-schema`;
- `--max-turns`;
- `--max-budget-usd`;
- `--allowedTools` and `--disallowedTools`;
- `--permission-mode`;
- `--session-id`;
- `--agents`;
- `--setting-sources`;
- `--no-session-persistence`.

The adapter must:

1. capability-probe these flags;
2. construct argv without a shell;
3. provide a bounded tool policy appropriate to assessment-only roles;
4. parse the actual result envelope;
5. capture session/runtime identity;
6. distinguish model failure from process failure;
7. enforce timeout and budget;
8. write completion evidence;
9. release the shared slot on every terminal path;
10. redact prompts or output fields that could contain secrets from diagnostic summaries.

The Codex assessment runner remains available behind the same interface. Do not regress it while adding Claude. The write-code support path remains parent-owned on both clients.

#### Before and after

- Before: the research controller shells out specifically to Codex, so copying the skill to Claude does not make Claude capable of running it.
- After: the playbook asks for an assessment role through one host-neutral contract; the selected adapter runs Codex or Claude and produces the same controller-owned result shape.

### Workstream D — client-neutral thread and ownership identity

#### Existing files to modify

- `scripts/work_memory.py`
- `scripts/prevention_owner_acceptance_fixtures.py`
- `scripts/prevention_owner_acceptance_producer.py`
- `tests/test_active_discovery_recovery_v1.py`
- `tests/test_correction_preservation.py`
- `tests/test_sequence_guard.py`
- `tests/test_work_memory.py`
- `tests/test_work_memory_bootstrap.py`

#### Required behavior

1. Introduce an explicit host/session identity provider.
2. Preserve `CODEX_THREAD_ID` compatibility for existing Codex records.
3. Accept a Claude session identity without renaming it to a Codex thread.
4. Persist host kind and host session identity in a stable owner representation.
5. Preserve ownership continuity across correction, successor run, recovery, and verification.
6. Reject ambiguous ownership instead of silently selecting the wrong active run.
7. Prove cross-client records do not collide.

The compatibility mechanism is append-only schema evolution:

- existing schema-v1 events and receipts retain their exact accepted fields, UUID validation, and hash calculation;
- no historical event is rewritten;
- new schema-v2 ownership events use `writer_id` as the neutral ledger UUID and add `writer_client_kind` plus `writer_session_id`;
- schema-v2 ownership/receipt hashes include the client kind, session identity, neutral writer ID, task, generation, and ownership-event identity;
- readers dispatch by schema version and validate v1 with the old algorithm and v2 with the new algorithm;
- a Codex-to-Claude ownership change uses the existing explicit release/handoff/claim lifecycle, producing a new v2 ownership generation. It never edits the v1 claim.

Acceptance must replay a frozen pre-change v1 ledger, validate its old receipts and hashes unchanged, perform a Codex-to-Claude handoff, restart/reload the ledger, execute correction/successor verification under the new owner, and reject a colliding Claude session from another host identity.

#### Before and after

- Before: Claude may have no usable owner identity or may masquerade as a Codex thread.
- After: work-memory ownership is client-neutral while old Codex records continue to resolve.

### Workstream E — zero-input sequence runner parity

#### Existing files to modify

- `skills/sequence-runner/SKILL.md`
- `scripts/sequence_intake_adapters.py`
- `scripts/sequence_intake_launch.py`
- `scripts/sequence_guard.py`
- `operations/sequences/sequence-intake-contracts.json` (`CREATE`)
- tests:
  - `tests/test_script_intake.py`
  - `tests/test_sequence_intake_adapters.py`
  - `tests/test_sequence_intake_launch.py`
  - `tests/test_sequence_intake_doc_projection.py`

#### Verify only

- `scripts/script_intake.py`
- `operations/sequences/SEQUENCES.md`
- every `operations/sequences/*/sequence.md`

A failed verify-only check stops for scope expansion; it does not authorize bulk sequence-document rewrites.

#### Required behavior

1. The projected Claude sequence skill tells Claude to launch the intake with no arguments.
2. Claude answers only the requested semantic value in the specified format.
3. The intake owns JSON-envelope and argv construction.
4. Every question includes response format, constraints, and an example.
5. The controller displays the exact derived operation before authorization.
6. The guard records the command source and rejects unsupported improvisation.
7. A no-argument violation fails clearly and does not execute the underlying sequence.

#### New or edited sequence plumbing

Adding or editing a promoted sequence is incomplete until all of these agree:

1. `operations/sequences/SEQUENCES.md` registry entry;
2. the promoted `sequence.md`;
3. dependencies and repository descriptors where required;
4. semantic intake specification;
5. adapter registration and deterministic argv derivation;
6. the generated semantic-intake entrypoint block in the sequence document;
7. guard/source registration;
8. selection/work-memory metadata;
9. focused adapter and launch tests;
10. projection/coverage test proving every promoted runnable sequence is wired.

The coverage test must enumerate the registry and fail when a newly promoted or materially edited runnable sequence has no usable intake mapping. An explicitly non-runnable composition/sub-sequence may be excluded only through a declared, tested reason.

`operations/sequences/sequence-intake-contracts.json` is the machine binding between each runnable sequence adapter and its caller interface. Each entry contains:

- `sequence_id`;
- `entrypoint`;
- `entrypoint_source_sha256` or a repository-owned source-receipt identity for cross-repository automation;
- `contract_version`;
- `semantic_fields`;
- `required_inputs`;
- `optional_inputs`;
- `argv_shape`;
- `adapter_id`;
- `adapter_source_sha256`;
- `verification_case_ids`.

Promotion/check recomputes the local source hash or validates the cross-repository source receipt. A changed entrypoint source invalidates the intake contract until its adapter compatibility is explicitly re-verified and the binding regenerated. The negative test changes a captured required caller parameter without changing the adapter and must fail before promotion or dispatch.

#### Before and after

- Before: Claude's stale skill encourages reconstructing commands and parameters.
- After: Claude never authors the machine input envelope; it supplies semantic answers and the shared deterministic controller does the rest.

### Workstream F — blocker resolution and work-memory parity

#### Existing files to modify

- `scripts/work_memory.py`
- the exact work-memory tests listed in Workstream D

#### Verify only

- `skills/blocker-catalog/**`
- `scripts/blocker_catalog.py`
- `operations/blockers/BLOCKERS.md`
- `tests/test_blocker_catalog.py`

`operations/blockers/BLOCKERS.md` remains generated output and is never edited as authority. A failed verify-only check stops for scope expansion.

#### Required lifecycle

For a deliverable blocker:

1. classify the failure;
2. create/update the durable blocker entry before mandatory remediation;
3. preserve practical symptom, exact evidence, impact, type, task/run identity, and stable boundary;
4. close the original run as failed where required;
5. record the correction;
6. create a fresh successor run paired to the correction;
7. rerun through the same path the operator uses;
8. update status through `open`, `fixed-awaiting-verification`, `verified`, and `closed` as evidence permits;
9. release all agent/run ownership;
10. render the generated blocker view.

Claude must use the same lifecycle and statuses as Codex. No Claude-only issue log is permitted.

#### Before and after

- Before: a stale Claude blocker skill can log issues without reliably driving correction and same-path closure.
- After: each blocker is a stateful remediation unit with a successor proof, not an ever-growing note.

### Workstream G — retire competing Claude command surfaces

#### Existing files to modify or delete

- `.claude/commands/review-fix-loop.md`
- `.claude/commands/verify-analysis.md`
- `.claude/commands/verify-plan.md`

The terminal disposition is locked:

- delete all three repository-local legacy command files after a read-only reference search proves only Claude discovery depends on them;
- rely on the same-named managed skill discovery for `verify-analysis` and `verify-plan`;
- route review work through the managed `review-playbook`/`verify-work` skills, not a replacement `.claude/commands` loop;
- during the separately approved global install, move unmanaged `~/.claude/skills/code-quality-review-loop` to the install transaction's recoverable quarantine outside Claude's skill-discovery root, preserving its original tree hash and rollback location. If quarantine is not approved, installation is blocked rather than leaving the competing controller active.

#### Required behavior

1. No command promises automatic commits.
2. No command creates an independent autonomous lifecycle.
3. Verify-analysis and verify-plan route to their canonical managed skills and preserve current role/ledger contracts.
4. Review routes to `review-playbook` or `verify-work` according to the real task, not a legacy generic loop.
5. A command cannot bypass PDI for write-code changes.
6. The unmanaged installed `code-quality-review-loop` is quarantined as specified above and is absent from Claude skill discovery after the approved install.

### Workstream H — Claude setup, hooks, and fresh-machine reproducibility

#### Existing files to modify

- `working-agreement/SETUP-claude.md`
- `working-agreement/SETUP-codex.md` only where shared installation behavior changes
- `.githooks/post-merge`
- `working-agreement/install-skills.sh`
- setup/installer tests

#### Required documentation and verification

`SETUP-claude.md` must describe:

1. directive hook installation without replacing other settings;
2. corpus/repo-memory and stop-hook preservation;
3. client projection generation and check-only mode;
4. repository-local parity validation;
5. explicit global-install approval;
6. transactional Claude installation;
7. fresh-session verification;
8. rollback/recovery;
9. unmanaged-skill reporting;
10. troubleshooting for missing CLI capabilities.

The setup must merge settings structurally or instruct a bounded manual merge. It must never overwrite `~/.claude/settings.json`, print credentials, or assume the repository is at a hard-coded user path.

The refresh path must also:

1. install/check both intended client projections rather than relying on the installer's default target;
2. prove the tracked hook is activated through `core.hooksPath` during machine setup;
3. remain idempotent;
4. fail visibly when either client projection is invalid;
5. never turn a pull into an unapproved mutation of a previously unreconciled client tree.

### Workstream I — isolate the parity verification harness

#### Existing files to modify

- `scripts/work_memory_contract_probe.py`;
- `tests/test_work_memory_contract_probe.py`;

#### Required behavior

1. Every probe run uses an isolated receipt and ownership ledger, or collision-proof run-scoped identities.
2. Repeating the probe produces the same result without cleaning the canonical ledger.
3. The probe cannot claim or mutate an existing real task.
4. The pre-change 107-pass/2-fail result is preserved as baseline evidence.
5. The corrected probe is green before it is used to judge Claude parity.

#### Before and after

- Before: a parity check can fail because an earlier probe already claimed its fixed task IDs.
- After: the same check can be repeated safely and failures describe the implementation under test, not leaked repository state.

## 7. Real acceptance scenarios

Repository-local focused tests are necessary but not sufficient. The final prototype must exercise these real behaviors.

| ID | Scenario | Required observable |
| --- | --- | --- |
| P-01 | Fresh Claude substantive task | First text is the G0 directive anchor with current revision, mode, scope, and exceptions. |
| P-02 | Fresh Claude write-code request | Routes to PDI and freezes an autonomy envelope before edits. |
| P-03 | PDI encounters an evidence gap | Pulls only the required generated support projection and records the source hashes. |
| P-04 | Fast-path local read/diagnostic | Does not invoke task intake, work-memory run lifecycle, or sequence machinery unnecessarily. |
| P-05 | Governed sequence request | Checks registry and launches `sequence_intake_launch.py` with zero args. |
| P-06 | Sequence asks for a value | Question contains answer format, constraints, and example; Claude answers only the semantic value. |
| P-07 | Derived sequence operation | Controller, not Claude, creates the JSON/argv and shows the exact operation before authorization. |
| P-08 | Newly registered runnable sequence missing an adapter | Projection/coverage validation fails before promotion or installation. |
| P-09 | Claude research role | Claude adapter launches a bounded assessment, parses structured output, records completion, and releases its slot. |
| P-10 | Claude role fails or times out | Failure is explicit; no slot leaks; no false PASS. |
| P-11 | Claude-owned work-memory run | Stable host/session owner is recorded without requiring `CODEX_THREAD_ID`. |
| P-12 | Deliverable blocker | Catalog entry precedes remediation; correction and fresh successor are linked; same-path verification closes it. |
| P-13 | Canonical skill changes after projection | Install/check fails on source-hash drift. |
| P-14 | Claude-only install without reconciliation | Installer refuses the mutation. |
| P-15 | Installed unrelated skill | Installer preserves it and reports it as unmanaged. |
| P-16 | Legacy Claude command invoked | It routes to the canonical controller and cannot auto-commit or bypass approval. |
| P-17 | Fresh Claude session after install | Installed skill inventory and projected hashes match the approved manifest. |
| P-18 | Existing Codex regression | Existing Codex PDI, playbook, sequence, work-memory, and blocker tests still pass. |
| P-19 | All managed capabilities | Every manifest row completes its assigned `CAP-*` behavioral scenario; hashes supplement but never replace behavior. |
| P-20 | Complete PDI support cycle | Bounded Claude research, plan, and review assessment roles return valid structured results with zero active slots on success and terminal failure; the parent PDI controller then applies one approved write-code-support delta to a temporary real fixture, runs its narrow proof, and resumes control. No assessment agent receives write authority. |
| P-21 | Historical work-memory compatibility | A frozen v1 Codex ledger and receipts replay unchanged; Codex-to-Claude handoff, restart, correction/successor continuity, and collision rejection pass under v2. |
| P-22 | Edited caller with stale adapter | A captured entrypoint contract changes a required input while its adapter remains unchanged; promotion/check fails closed. |
| P-23 | Prompt-submit and Stop hooks | An isolated structural settings merge preserves unrelated hooks; directive, corpus, repo-memory, and Stop paths run against temporary helpers, prove expected/fail-open behavior, and do not mutate production memory. |
| P-24 | Post-merge refresh | In an isolated temporary home/checkout, an activated tracked hook checks both client projections, refreshes both only after reconciliation, preserves unmanaged skills, and fails visibly on drift. |
| P-25 | Repeatable parity probe | Two consecutive work-memory contract-probe runs pass without canonical-ledger cleanup or ownership collision. |
| P-26 | Installed fresh-session routing | A fresh installed Claude session proves G0 anchoring, PDI routing, one zero-input governed intake, and legacy-controller absence. |

For the assessment portions of P-09, P-10, and P-20, the test harness must use bounded spend/turns and the smallest real prompt that proves the runtime contract. It must not start an open-ended multi-hour agent run. P-20's write-code portion runs in the parent PDI controller against an approved temporary fixture and is not credited from a subagent response. P-23 uses temporary no-secret helpers through the existing hook environment overrides; `MK_AUTOCAPTURE=1` is set only with a temporary `MK_AUTOCAPTURE_HELPER`, and corpus/repo helpers are likewise redirected so production memory is never written.

## 8. Verification order

The verification commands are locked to the repository launcher and checked-in entrypoints:

1. Shell syntax for the changed wrappers:
   `bash -n working-agreement/install-skills.sh .githooks/post-merge scripts/run_pytest.sh`
2. PDI support-projection drift:
   `python3 skills/prototype-driven-implementation/scripts/generate_support_projections.py --check`
3. Projection, installer, and runtime adapter:
   `scripts/run_pytest.sh tests/test_client_skill_projections.py tests/test_host_agent_runtime.py tests/test_claude_parity.py`
4. Existing installer validation/recovery and promotion integration:
   `scripts/run_pytest.sh tests/test_install_skills.py tests/test_validate_skills.py tests/test_promote_plan_playbook.py tests/test_promote_research_playbook.py tests/test_research_playbook_v2.py tests/test_sequence_guard.py`
5. PDI support projections:
   `scripts/run_pytest.sh tests/test_prototype_support_projections.py`
6. Sequence intake, caller binding, and documentation projection:
   `scripts/run_pytest.sh tests/test_script_intake.py tests/test_sequence_intake_adapters.py tests/test_sequence_intake_launch.py tests/test_sequence_intake_doc_projection.py`
7. Work-memory, blocker, and repeatable probe:
   `scripts/run_pytest.sh tests/test_work_memory.py tests/test_work_memory_contract_probe.py tests/test_blocker_catalog.py tests/test_discovery_candidate_reconciliation.py tests/test_discovery_promotion_lifecycle.py tests/test_sequence_guard.py`
8. One bounded live Claude capability probe derived from captured `claude --help`, using `--print`, structured output, a positive `--max-turns`, a small `--max-budget-usd`, explicit allowed/disallowed tools, and a temporary ledger. Record the exact argv without secrets before running.
9. Complete repository suite:
   `scripts/run_pytest.sh`
10. Check-only projection/parity report:
   `python3 working-agreement/project_client_skills.py check --client claude --installed-root "$HOME/.claude/skills"`
11. After separate approval, transactional installation followed by P-01 through P-26 in a fresh Claude session or isolated temporary home as each scenario specifies.
12. Rerun step 9 and Codex-specific P-18 after the approved install.

Direct `pytest`, `python -m pytest`, and `uv run pytest` are prohibited in this repository; `scripts/run_pytest.sh` is the repository-owned launcher.

Every command must record:

- working directory;
- command authority: checked-in config, repository launcher, or captured `--help`;
- exit code;
- relevant observable;
- artifact/log path;
- whether external state or paid model execution occurred.

## 9. Failure handling and rollback

### Projection or test failure

Do not install. Preserve:

- canonical source hash;
- projection manifest hash;
- generated tree hash if available;
- failing test/validation output;
- exact parity disposition involved.

Fix the canonical boundary or projection rule. Do not patch the installed Claude directory.

### Interrupted install

Use the existing installer journal and recovery behavior. Extend it rather than creating a second installer. Recovery must restore every original managed destination or remove a newly introduced destination whose install never committed.

### Post-install behavioral failure

1. mark the install verification failed;
2. restore the previous installed managed trees from transaction evidence;
3. verify restoration hashes;
4. open/update a blocker entry if this prevents the approved outcome;
5. reproduce through a repository-local captured case;
6. fix the canonical/projection/runtime boundary;
7. repeat check-only verification before requesting another global install.

### Claude CLI capability mismatch

If the installed Claude version lacks a required flag or returns a changed envelope:

1. record the exact `claude --version` and `claude --help` evidence;
2. fail the capability probe;
3. do not emulate the missing safety control silently;
4. determine whether the adapter can provide an equivalent bounded contract;
5. otherwise stop as `BLOCKED`.

## 10. Delivery increments

These are verification-sized increments, not speculative feature milestones. PDI may reorder them only when real evidence shows a dependency differs.

1. **Parity detector** — read-only inventory and complete dispositions.
2. **Projection builder** — deterministic staging output and drift failure.
3. **Installer gate** — all Claude mutations require complete reconciliation.
4. **PDI projection** — Claude routes implementation through the central controller.
5. **Runtime adapter** — one bounded Claude assessment role completes and releases.
6. **Identity adapter** — Claude work-memory ownership and recovery work.
7. **Sequence parity** — zero-input intake and promotion/edit coverage work from Claude.
8. **Blocker parity** — one blocker closes through correction and successor verification.
9. **Legacy retirement** — old Claude commands cannot compete.
10. **Fresh-machine setup** — documented, checkable, rollback-safe installation.
11. **Isolated verification harness** — repeated probes do not collide with canonical ownership state.
12. **Accumulated review** — all real cases plus Codex regression.

Each increment must end in a runnable promoted prototype with evidence. Do not accumulate all changes and defer verification to the end.

## 11. Cost and risk

This is a substantial cross-client controller change, not a skill-copy operation.

Main costs:

- building and testing the projection/reconciliation contract;
- isolating agent runtime and session identity assumptions;
- proving real Claude role execution without long runs;
- keeping existing Codex behavior unchanged;
- validating sequence promotion/edit wiring across the whole registry.

Main risks:

- textual parity that still fails at runtime;
- a projection system becoming a second authority;
- installer mutation before reconciliation;
- slot/run leaks on Claude timeouts;
- blind replacement of intentionally Codex-specific canary behavior;
- legacy commands continuing to bypass the central controller;
- global settings being overwritten.

Risk controls are the one-authority rule, source hashes, staged generation, capability probes, bounded live cases, transactional installation, and fresh-session verification.

## 12. Definition of done

Claude may report this work complete only when all of the following are true:

- every managed skill has one valid current parity disposition;
- every managed skill has passed its assigned bounded Claude behavioral scenario; no skill is accepted by hash alone;
- Claude has a working installed PDI controller;
- all generated support projections verify against current source hashes;
- Claude write-code routing enters PDI;
- Claude research/plan/review support roles can execute through the host-neutral runtime contract;
- zero-input sequence intake works from Claude and Claude never constructs the machine envelope;
- every promoted runnable sequence is covered by intake/promotion validation;
- work-memory identity and blocker closure work from Claude;
- historical v1 Codex work-memory data and receipts replay unchanged through the versioned identity reader;
- research, plan, and review assessment support return control to PDI from Claude with zero leaked slots, and parent-owned write-code support applies and proves an approved real-fixture delta without delegating write authority;
- directive, corpus, repo-memory, and Stop hooks are structurally preserved and pass isolated behavior/fail-open checks;
- a stale sequence adapter is rejected when its bound caller interface changes;
- legacy command surfaces cannot bypass the current architecture;
- repository-local focused and full tests pass;
- the work-memory contract probe is isolated and repeatable, with the pre-existing ownership-collision defect closed;
- all bounded real acceptance scenarios pass;
- installed Claude hashes match the approved projection manifest;
- the activated post-merge path has proved a reconciled two-client refresh in an isolated checkout;
- existing Codex scenarios still pass;
- global install, commit, and push have only occurred under their own explicit approvals;
- the final report leads with practical before/after outcomes and names any remaining non-gap exclusions.

## 13. Initial instruction for Claude

Use the following as the first implementation instruction after Kamen supplies this document:

> Read `working-agreement/DIRECTIVES.md`, the canonical `prototype-driven-implementation` skill, and `Tasks/claude-parity-handoff/HANDOFF.md`. Treat PDI as the central controller even though it is not yet installed in Claude. First perform read-only Prototype 0 and present a bounded autonomy envelope covering only this repository and the handoff paths. Do not edit until I approve that envelope. After approval, drive the parity work yourself through runnable promoted prototypes, using the real Claude CLI capability surface and the shared deterministic sequence intake. Stop separately for global `~/.claude` installation, commit, push, deployment, credentials, destructive work, another repository, or external messages.

## Appendix A — complete managed capability inventory

The projection manifest must cover exactly the current entries in `skills/managed-skills.txt`, and validation must detect future additions automatically:

1. `_shared`
2. `auto-capture`
3. `blocker-catalog`
4. `corpus-add`
5. `critic-foundry`
6. `doc-gap-closure-loop`
7. `phase-categorization-foundry`
8. `phase-ledger-category-contract-foundry`
9. `phase-ledger-contract-hardener`
10. `plan-playbook`
11. `playbook-convergence-loop`
12. `producer-foundry`
13. `prototype-driven-implementation`
14. `remote-mcp-operator`
15. `remote-mcp-user-admin`
16. `requirements-coverage-gap-loop`
17. `requirements-satisfaction-gap-loop`
18. `research-playbook`
19. `reproduce-first-verify`
20. `review-playbook`
21. `sequence-runner`
22. `shell-canary-foundry`
23. `shell-canary-runner`
24. `task-intake`
25. `task-workflow`
26. `verifier-foundry`
27. `verify-analysis`
28. `verify-plan`
29. `verify-work`
30. `working-agreement`
31. `write-code-playbook`

This appendix is a review snapshot, not a second manifest. `skills/managed-skills.txt` remains the machine authority.

### Locked disposition for the current 31 entries

All 31 current entries are `SHARED_IDENTICAL`.

That disposition applies to the corrected canonical source, not to the stale installed Claude copy. Host assumptions identified in this handoff are fixed at the canonical boundary or isolated behind `host_agent_runtime.py`; the resulting canonical tree is then installed byte-for-byte into both clients. There are no current `GENERATED_CLIENT_PROJECTION` or `CLIENT_NOT_APPLICABLE` rows. The projection machinery exists to make any future divergence explicit and hash-bound rather than allowing an installed fork.

The projection manifest must assign bounded behavioral scenario groups as follows:

| Scenario group | Managed entries | Required Claude proof |
| --- | --- | --- |
| `CAP-GOVERNANCE` | `working-agreement`, `task-intake`, `task-workflow` | Directive routing, fast-path exclusion, governed-path selection, and task-folder behavior. |
| `CAP-PDI` | `prototype-driven-implementation`, `research-playbook`, `plan-playbook`, `write-code-playbook`, `review-playbook`, `playbook-convergence-loop` | PDI ownership plus bounded research, plan, and review assessment handoffs, followed by one parent-owned approved write-code delta and proof. |
| `CAP-VERIFY` | `verify-analysis`, `verify-plan`, `verify-work`, `doc-gap-closure-loop`, `requirements-coverage-gap-loop`, `requirements-satisfaction-gap-loop` | Each skill is discoverable from Claude and runs its bounded controller/assessment entry without Codex-only paths or slot leaks. |
| `CAP-PERSONAS` | `producer-foundry`, `verifier-foundry`, `critic-foundry`, `phase-categorization-foundry`, `phase-ledger-category-contract-foundry`, `phase-ledger-contract-hardener` | Each skill resolves its referenced scripts/contracts and completes one read-only fixture-based invocation from Claude. |
| `CAP-OPERATIONS` | `sequence-runner`, `blocker-catalog`, `reproduce-first-verify`, `shell-canary-foundry`, `shell-canary-runner` | Zero-input intake, blocker successor closure, captured reproduction, and operation of intentionally Codex-targeted canaries by Claude without rewriting their target. |
| `CAP-REMOTE` | `remote-mcp-operator`, `remote-mcp-user-admin` | Package discovery and a no-secret dry/captured intake path; no real remote mutation is needed for parity installation. |
| `CAP-MEMORY` | `auto-capture`, `corpus-add` | Isolated capture/add contract and fail-open hook behavior with test helpers; no production corpus mutation. |
| `CAP-SHARED` | `_shared` | Agent ledger, host runtime, verification ledger, and convergence-state focused tests pass for both hosts. |

Every manifest row names at least one scenario group. A tree-hash match without its assigned behavioral proof cannot reach `PASS`.

## Appendix B — frozen inventory evidence

Observed at `2026-07-24T06:47:35Z`.

Roots:

- canonical: `/Users/kamenkamenov/memory-knowledge/skills`;
- installed Claude: `/Users/kamenkamenov/.claude/skills`.

Authority hashes:

- `working-agreement/DIRECTIVES.md`: `a860591a4f98037b959b9cf48479809570cac3915aa66855c1bf804ca1bb6d31`;
- `skills/managed-skills.txt`: `49878a96b2489eb3209dc318ac201cafe7ac533a2dbd41ebcdeb0a3dbdfb8a20`.

Claude capability observation:

- `claude --version`: `2.1.126 (Claude Code)`;
- `claude --help` SHA-256: `05e3aebedeb12554d1f16a722fe5574534aea7cbc1ba3f8223809cc1e386e674`;
- `git config --get core.hooksPath`: no configured value.

Tree hashes use the exact `tree_hash()` implementation in `working-agreement/install_skills.py`: sorted repository-relative file paths plus file bytes.

| Managed entry | Canonical SHA-256 | Installed Claude SHA-256 | State |
| --- | --- | --- | --- |
| `_shared` | `a7852647f92e8a41e4d9d852c556984ac57298b2f088b9cb53c819e6945e6f21` | `5c2d54633ff52e1da5930d6f9d9fcc61782ed89c75834b7f5d4ac13fcb7fa969` | DRIFT |
| `auto-capture` | `dc8696b88f693ba58bf64a874fc474b6cb1fd4489627a80ac8aa411dbf890f36` | same | MATCH |
| `blocker-catalog` | `769b2c7fe0d02c4ff9c8941441021d2e71a1484680af90fcf4a425522d19f46e` | `f61bafdd8a6a50f96bcd7570bd6be46d9bf9e734a182484c48aa1ade3fc19821` | DRIFT |
| `corpus-add` | `159f0609a05a4e84b76a1f5d94e0f9eedb8cd92f2489b3b6e5a2c667c98240b0` | same | MATCH |
| `critic-foundry` | `73aeccec42579ddf49d4711ba0ea80aa60c530e8d864d542944b35777aed6393` | same | MATCH |
| `doc-gap-closure-loop` | `cc99f04b6fe7159b14e5a05dd672f280fad7df0b12a65cb220ce0a9a7f3922a3` | same | MATCH |
| `phase-categorization-foundry` | `c3b261e89669a814719ccda58ecf3620c7b5e8b1e5915a0db8fa5453f36021c4` | same | MATCH |
| `phase-ledger-category-contract-foundry` | `b849c5b1f5acffe5e05eebbaac420d32d7a3d98e4e6820e43082b36d66fce6c8` | same | MATCH |
| `phase-ledger-contract-hardener` | `a23aa640046866baa7aa1ff5ec3a50f3a85d1ef4f5e3fbed4bd16f9ab6e0b1cf` | same | MATCH |
| `plan-playbook` | `243c47dee2c3f52cd1f9a55a2fa757726ff8f007a5f387e8ece77a69dab19997` | `72d1d8234fe6a37b51c1efad0f1634fb28f55e2c2fffea1865ed4964af0c777b` | DRIFT |
| `playbook-convergence-loop` | `bd47ff282f7214855de871f5f89b4d21ab6efa3eec19dafdf2fda34cb0255576` | `f4d0938efbb23da50dda39f261df76ce647a68bf93dc0a737d4f5fa77b88cabf` | DRIFT |
| `producer-foundry` | `ce6080ff7f8422d6f72bb1b15390ec3f498830214d79a1d3e169fd411c3de35e` | same | MATCH |
| `prototype-driven-implementation` | `d725a79f1da3503727ad92f59508a46a5367f1199f8aeff9b7ab045d7c8ae9ee` | absent | MISSING |
| `remote-mcp-operator` | `5a943d4f437749e047a116cdf808bc51b53179c6d89d65f0d3dc1eb4b21c6cbf` | same | MATCH |
| `remote-mcp-user-admin` | `b4e43e25d22d3c3de0baad516e9fabd815507feb68807d73c615ecf5c8d6bf84` | same | MATCH |
| `requirements-coverage-gap-loop` | `ccc931dda0ad4338424a5273a3c7101ceca80bbd8e5830726c86ec5b89d72e4c` | same | MATCH |
| `requirements-satisfaction-gap-loop` | `6838d24a5b393ba22a1e75a187d17c64fb17c0e0e0895e7e765b01989a8ad1ee` | same | MATCH |
| `research-playbook` | `f7cf5914bf6c6a0a7ebed13f45a65c52b8f39a85299b18ab886d802cd1ad6f23` | `9d29adeacbd5bbbc7982242c8cdda6f29d39a54244f27e706788b95f8a9c72fd` | DRIFT |
| `reproduce-first-verify` | `831fa54be27e785291b628e1951d8d89a60ef749a512689f3dbf50e218543c99` | same | MATCH |
| `review-playbook` | `edbc7ddc6e22bed96484f0f53bbda7781be7121635d033229e40761adcd2190e` | same | MATCH |
| `sequence-runner` | `1f6cb097eaaa39c22c7355984a2140b64eba9ad64996beca9d00e0b7ce79f688` | `cffae00601f14086712d0573bb22bc12ed29ffc5177eb428a629f7501180078d` | DRIFT |
| `shell-canary-foundry` | `20d0c0422f70c2cf17413f14dcabcf87c607e11d77e32489210bda88205ee1ec` | same | MATCH |
| `shell-canary-runner` | `1670340defadec7928dc4e851270f280459511fa29350d9859b580294cd3ac4f` | `be02771c1ab213822504055bb3e98eb7a52d9c78b2c738885af128e9a6f7964c` | DRIFT |
| `task-intake` | `44a7fb39dccd98b2d1ee5fde6bdef5ab8d71b983123b266e68eef95d0c397c0d` | `bf92c0689cc621f62f261b84c57e4976569a381d8038a4d7eb9ffd0c25acccf9` | DRIFT |
| `task-workflow` | `58610cceb740aa69a9c7e6857257d02e30f727f368552ec8ef70e2c383c3665e` | `38f6a2accd96cf5a7e1a6f1ba19c4f60fbffde89de736d17fda23b3d871607dc` | DRIFT |
| `verifier-foundry` | `1ac2bf7b99bfd6f30efec4a6c272584ceffe4f7e5fc14f8008503b2301a29c25` | same | MATCH |
| `verify-analysis` | `507aff270614ef2947b6f9ea9bdb04fa6ec8729835195853dea9ca22b7e9bca5` | same | MATCH |
| `verify-plan` | `40d7f8244fa36080b6e24eebc15a311a91dbc11fe06b11444300c94ff4d68246` | `05c35344784271a76d6d2f3e2f5e8d95d764bb773d4299507b96d1dbdf58950a` | DRIFT |
| `verify-work` | `181d28fec360aaaba1fbb4033aa082e053aa8b3e1f7e21bd102d795c451bde91` | same | MATCH |
| `working-agreement` | `36f57a20601c1b970d11d235bcb58f3e99959e2e82db3abbeb87e506a74d96f1` | `e3f9f04e4ce0b5787b517fec7e16113cc107d68641ef773c92379c079db77827` | DRIFT |
| `write-code-playbook` | `1e30a34e0056edb4f0f33b5746f49de36818386ac414e4aae75ae97d1242401e` | `0bb9bf9c4c5a7ca3458b9db5f4c3765c55f93981cc010b9c94ae0d7bad03905a` | DRIFT |

Reproduction procedure:

1. Read names from `skills/managed-skills.txt`.
2. For each name, call the repository installer's `tree_hash()` on the canonical and installed roots.
3. Compare hashes and print `MATCH`, `DRIFT`, or `MISSING`.
4. Run `claude --version`, hash the bytes from `claude --help`, and read `git config --get core.hooksPath`.

Mutable external-state observations must be refreshed by Prototype 0. A changed result is drift evidence, not a contradiction to this timestamped snapshot.
