---
name: reproduce-first-verify
description: Use when fixing a recurring defect whose live verification point is far into a long or expensive run. Capture the exact live failing state, build the cheapest reproduction that exercises the real code path with captured inputs, prove red-before and green-after, then perform one live confirmation through the project's fastest valid re-entry point. Do not use for cheap one-off verification or when no real failing state has been captured.
---

# Reproduce-First Verify

Shorten expensive defect loops without weakening evidence: reproduce at the tightest viable boundary, prove the fix there in seconds, then pay for one live confirmation.

## Use Boundary

Use only when both conditions hold:

1. The live verification point is minutes or hours into a run.
2. The defect is a recurring class, so the reproduction will be reused or materially reduce repeated live runs.

This skill governs verification technique. It composes with the working agreement, `write-code-playbook`, and `playbook-convergence-loop`; it does not expand edit, commit, deployment, or live-run authorization.

## Workflow

### 1. CAPTURE

Capture the exact failing state from the live failure: log dumps, state-file JSON, failing dictionaries/arguments, and the exact error classification. Build the reproduction only from captured evidence. Never guess or synthesize the inputs that make the case fail.

If the failing state cannot be captured, stop: a trustworthy reproduction cannot yet be built.

### 2. REPRODUCE At The Tightest Viable Boundary

Use the cheapest boundary that still runs the real failing code path:

1. **Rung A: in-process test.** Import and call the real function or method with captured state. In Python repos, prefer a focused command such as `uv run pytest tests/<file>::<test>`.
2. **Rung B: subsystem mini-harness.** Boot only the failing component when cross-component or async behavior is essential. Mock only true external edges such as a foreign service, network, or clock; never mock the logic under test.
3. **Rung C: full live run.** Use only for the final confirmation, not as the fix iteration loop.

Escalate only when the lower rung cannot express the defect while preserving the real path.

### 3. TRUSTWORTHINESS GATE

Do not trust a green reproduction until all three checks pass:

- [ ] **Same code path.** The reproduction calls the real function or boots the real subsystem. It does not reimplement the behavior; mocks exist only at true external edges.
- [ ] **Real captured inputs.** Every material input/state came from the live failure, not from an invented convenient case.
- [ ] **Red-before / green-after.** The reproduction fails on pre-fix code and passes after the fix. A test that was already green does not verify the fix.

If any check fails, say that the reproduction is not a valid proxy and do not claim the fix is verified.

### 4. VERIFY

Run the focused reproduction and preserve raw red-before and green-after evidence. Confirm that the transition is caused by the intended fix rather than a changed fixture, bypassed path, or weakened assertion.

### 5. INSERT + ONE Live Confirmation

Insert the verified fix, then run one live confirmation through the closest valid re-entry point. For `mcp-agents-workflow`, verified flags in `scripts/greenfield_drive_dag.py` are:

- `--resume-from-checkpoint` with `--expected-spec-hash`: skips N1, N2, and the long harvest, then drives the DAG directly.
- `--validate-only` and `--start-validation-round k`: enter the live-validation loop against the already merged repository/branch.
- `--start-feature-index k`: resume the DAG at feature k.

Treat a new layer exposed by live confirmation as a new defect. Return to CAPTURE with that layer's evidence.

### 6. REPORT

Report:

- boundary rung and why it was the lowest viable rung;
- same-code-path evidence;
- captured-input provenance;
- raw red-before and green-after results;
- the single live-confirmation command/result, or the exact authorization/environment blocker;
- any newly surfaced defect as a separate capture cycle.

## Independent Verification

When independent review is required, use bounded assessment subagents managed by the shared `skills/_shared/agent_slot_ledger.py` ledger (resolve it from the installed skill root on the active client, or from the canonical repository). Initialize a new ledger with `init <ledger.json> --max 1`, or validate the existing task ledger before reuse. The parent orchestrator performs `guard -> acquire -> spawn -> bind-agent -> wait/collect -> mark-completed -> host-accurate terminal step -> mark-closed -> release -> status`. The terminal step is the host's real completion boundary: runtime close_agent on Codex; on Claude, process-terminal completion evidence via `skills/_shared/host_agent_runtime.py` (no invented close operation). Require zero active slots at the boundary, then `compact` released tombstones if retention is unnecessary. A completed runtime agent remains open until explicitly closed; never use `reap` to erase a live or unknown slot. Reviewers are assessment-only and receive captured evidence and source/runtime access without producer rationale.

## Honest Limits

1. You can reproduce only a failure that is already reachable. A masked path needs a live run to surface it first.
2. Emergent concurrency, integration, and timing defects commonly require one live surfacing before a rung-B harness can replay them.
3. Reproducing the fix does not prove the whole run succeeds. One fix can reveal the next layer; the single live confirmation remains necessary.
4. A harness costs time. Use it for long live loops and recurring defects, not trivial one-offs.

## Real Examples

### Archetype: GF-N3-LEASE-ORPHAN

`tests/test_greenfield_n3_drive_feature.py::test_reclaim_uses_metadata_run_id_when_workflow_run_id_none` passes the captured orphan shape (`workflow_run_id=None`, holder id in `metadata_json.run_id`) to the real `_release_precode_chain_retriable_task_lease` in `src/workflow_orch/mcp_server.py`. The rung-A test runs in roughly 0.1 seconds and demonstrated red-before/green-after. The later roughly 75-minute live drive returned the same `released: True`, so live was confirmation rather than the discovery loop.

### Counter-Example: GF-N3-RESEARCH-ACTIVE-RUN-NOT-ADOPTED

This path became reachable only after the lease fix removed the masking failure. Live integration then showed orphaned research runs accumulating, active-sibling count `0 -> 1 -> 2 -> 3`, and a halt after retry `3/3`. It illustrates the first limit: live had to surface the new layer before captured evidence could support a rung-B reproduction.
