# Mechanical-error prevention system: implementation analysis

## Outcome

The repository can host the authoritative prevention controller, typed sequence-owner registry, durable transition/effect journal, mandatory correction selector, learning lineage, budget admission, Codex project hooks for supported tool classes, and acceptance telemetry. The stable design is one controller in front of all registered sequence owners, backed by the existing branch-persisted work-memory ledger. Extending the current opt-in guard or adding more parser aliases would not close the system-wide gaps.

The implementation must fail closed when the active host cannot prove a pre-dispatch boundary for every granted action class. Official Codex project hooks can enforce Bash, `apply_patch`, and MCP through `<repo>/.codex/hooks.json`; they do not cover every unified-shell, WebSearch/browser, subagent, or non-MCP remote action. Therefore the repository must never label a run `FULLY_GOVERNED` unless unsupported classes are structurally withheld by the launching host or a future authoritative hook is present. A normal Codex session that still grants uncovered classes remains visibly `HOST_CAPABILITY_UNSATISFIED`, not silently “protected.”

## Confirmed current state

- `operations/sequences/SEQUENCES.md` contains 25 rows but is prose-rendered and permits composite or non-standalone owners.
- `scripts/work_memory.py` already provides a closed event-shape table, atomic append transaction, receipt binding, correction identities, same-path verification, and branch-persisted ledger files.
- `scripts/sequence_guard.py` and `scripts/sequence_checked_exec.py` are opt-in and accept a command string or arbitrary remainder argv.
- `scripts/sequence_observer.py` observes a run after execution; its end-to-end test proves later post-hoc recognition, not pre-action mandatory reuse.
- `scripts/discovery_promotion_lifecycle.py`, `scripts/discovery_candidate_reconciliation.py`, and `scripts/sequence_promote.py` preserve approval and promotion authorities that must remain intact.
- `skills/research-playbook/scripts/research_run.py` is the strongest durable-controller pattern, but its admission formula omits mandatory roles and terminal/materialization/retry cost.
- No repository-roots registry is currently available at `~/.config/memory-knowledge/repositories.json`, so external automation internals cannot be credited. Their adapters require explicit black-box evidence before 25/25 completion can pass.
- The working tree is already substantially dirty. Implementation must limit edits to the approved surfaces and compare each touched file against the pre-plan snapshot; unrelated changes must be preserved.

## Selected architecture

### 1. One authoritative controller

Create `scripts/prevention_controller.py` as the sole public entry point for governed sequence execution. Its closed operations are `inspect-host`, `register-intent`, `dispatch`, `resume`, and `report`. `dispatch` accepts a sequence id plus only the named typed parameters declared for that sequence; it never accepts a command string, arbitrary argv, request JSON, or text patch.

Every registry row resolves to exactly one owner adapter. Multiple existing scripts may remain internal implementation details, but callers cannot invoke a composite by reconstructing those steps. A non-standalone subsequence resolves to its parent owner and is rejected as a standalone dispatch.

### 2. Typed canonical registry

Add a machine-owned owner registry under `operations/prevention/`. Each row has an exact sequence id, owner kind, handler symbol, closed parameter schema, fixed argv token templates assembled only inside the adapter, action classes, long-unit cost contract, effect-reconciliation method, and terminal pass signal. `SEQUENCES.md` remains the human projection; runtime selection stops parsing its table.

Static JSON storage is not the prohibited behavior. The prohibited behavior is an operator or model constructing/patching JSON to make a governed operation execute. Registry data is loaded through an exact schema and unknown keys fail before effects.

### 3. Existing work-memory ledger as authority

Extend the existing event contract rather than create a second truth. New event families record intent eligibility, host capability, selection/rejection, predecessor prohibition, budget admission/rejection, transition preparation/commit, effect preparation/commit/reconciliation, registered reuse, prevented failure, and classified timing. All events carry task/run/branch/worktree ownership plus a stable compatibility or effect key.

The controller writes `PREPARED` before an effect and `COMMITTED` after it. Resume reconciles a prepared effect by its adapter-owned effect identity before deciding to execute, skip, or fail visibly. A different branch/worktree/run cannot consume the journal.

### 4. Pre-dispatch selection and host enforcement

The selector runs before any execution claim. It resolves, in order: prohibited predecessor, verified successor, promoted registered implementation, registered owner, or visible rejection. A same-path-verified correction atomically records the predecessor prohibition and successor binding; a later compatible action cannot choose the predecessor.

Project-local Codex `PreToolUse` hooks feed supported Bash, `apply_patch`, and MCP calls into the selector. Unsupported action classes are not treated as intercepted. The controller's host-capability admission refuses `FULLY_GOVERNED` startup whenever an uncovered class is granted. Launchers that can provide a structural tool manifest may declare the class withheld only with testable evidence.

### 5. One learning lineage

Use a single lineage id and compatibility key to join intent, attempted action, failure fingerprint, diagnosis, correction, same-path verification, discovery, promotion, registered verification, and later pre-action reuse. Keep the existing discovery qualification, approval, promotion, and registered-verification predicates; the new controller coordinates them but does not weaken them.

### 6. Full-unit admission

Define a strict `UnitBudget` with productive work, every mandatory gate/role, adjudication, materialization, terminal emission, and bounded retry allowance. A long owner declares its complete unit before launch. Admission is one durable atomic decision; one unit below the required amount records rejection and launches no role or effect.

### 7. Acceptance telemetry

Generate all acceptance metrics from canonical ledger events over an explicit fixed window. The report includes numerator and denominator event ids, exclusion classifications, and insufficient-evidence status. It must not manufacture a passing ratio from synthetic fixtures. Mechanical overhead includes local retries, reconstruction, malformed-input recovery, guard/selector work, and correction work; only separately classified approval wait, external service/rate-limit wait, and productive model/domain execution may be excluded.

## Scope boundary

In scope: `memory-knowledge` controller, contracts, canonical registry and projection, work-memory events and queries, supported Codex project hooks, adapters for all 25 declared rows, tests, and task-local acceptance evidence.

Out of scope without separate approval: edits in `mcp-agents-workflow` or any external automation repository, user-global Codex configuration, deployment, secrets, commits, pushes, and phase-ledger contracts. External owners are exercised through black-box adapters when their configured repositories are available; absence is reported as evidence unavailable, never counted as a pass.

## Implementation risks and containment

1. **Host coverage:** a repository hook cannot intercept every Codex action class. Containment is fail-closed host admission, not an advisory warning.
2. **External owner availability:** 25/25 cannot be claimed from mocked internals. Containment is a black-box evidence record per owner and an explicit incomplete terminal result when a repository is unavailable.
3. **Ledger migration:** adding event types must not reinterpret existing events. New fields apply only to new event types; legacy readers remain valid and migration tests replay the current ledger.
4. **Dirty-tree overlap:** several authority files already contain user/current-session edits. Apply narrow patches and review the accumulated surface from a recorded baseline; never replace whole files mechanically.
5. **False metric success:** fixtures may verify formulas but cannot satisfy representative-runtime thresholds. Acceptance reports distinguish contract-test PASS from real-corpus PASS.

## One-shot planning decisions

- The canonical runtime registry is typed machine data; Markdown is a generated human view.
- The existing work-memory ledger remains the only durable event authority.
- The controller owns selection, admission, effect reconciliation, terminal emission, and resume.
- Existing promotion approvals remain mandatory.
- Unsupported host action classes cause startup rejection unless demonstrably withheld.
- External automation evidence is black-box and mandatory for a 25/25 claim.
- No compatibility alias garden is introduced for malformed model output or legacy command strings.
