# MCP Agents Workflow V4 Integration Guide
## How `mcp-agents-workflow` Should Use The New `memory-knowledge` Upgrades

**Audience:** another LLM or engineer updating `mcp-agents-workflow`  
**Applies to:** the live `memory-knowledge` MCP server already deployed from this repo  
**Goal:** make the external orchestrator actually use the new adaptive V4 capabilities instead of continuing to behave like a pre-upgrade client

---

## 1. Why This Upgrade Exists

`memory-knowledge` now exposes a stronger advisory layer on top of workflow telemetry and triage memory.

Before this upgrade, an orchestrator could:

- persist runs and validator results
- read historical summaries
- search prior triage cases
- make mostly local routing and clarification decisions

After this upgrade, the orchestrator can also ask the server for:

- route quality by request/workflow shape
- the strongest required clarification policy for a route
- convergence interventions when a run is looping or degrading
- normalized playbooks for recurring failure signatures
- actor-aware adaptation guidance
- rollout/governance posture for policy adoption

These are advisory tools. They do not replace the orchestrator. They improve the orchestrator's decisions.

If `mcp-agents-workflow` makes no changes, old behavior should still work, but the new adaptive behavior will remain largely unused.

---

## 2. The New Tool Surface To Integrate

The minimum V4 tools to adopt are:

- `get_required_clarification_policy`
- `get_outcome_weighted_routing_summary`
- `get_convergence_recommendation_summary`
- `get_failure_mode_playbooks`
- `get_actor_adaptation_summary`
- `get_policy_governance_rollout_summary`

You should also keep using the existing tools that these depend on operationally:

- `triage_request_with_memory`
- `finalize_triage_outcome`
- `save_workflow_run`
- `save_workflow_phase_state`
- `save_workflow_validator_result`
- `save_workflow_finding`
- `save_workflow_finding_decision`
- `get_workflow_run`
- `list_workflow_runs_by_actor`

The V4 tools are only as useful as the persisted workflow and triage facts behind them.

---

## 3. Ownership Boundary

### `memory-knowledge` owns

- persistence
- normalization
- historical summaries
- policy and guidance synthesis

### `mcp-agents-workflow` owns

- when to call tools
- how to interpret the returned guidance
- actual route selection
- actual clarifying-question generation
- retry policy
- convergence policy
- user-facing messaging

Do not move server-side policy synthesis into the external orchestrator. Call the tools instead.

---

## 4. Mandatory Integration Changes

The external orchestrator should make these behavior changes.

### 4.1 Pass `actor_email` wherever available

When the triggering user or operator is known, pass `actor_email` into:

- `triage_request_with_memory`
- workflow-run writes when actor identity is available
- any actor-scoped read flow that supports actor grouping

Why:

- actor adaptation depends on it
- entropy and loop targeting are better with it
- recovery and grouping become more accurate

If `actor_email` is omitted, the server will still work, but adaptive guidance becomes weaker and may bucket behavior under `unknown`.

### 4.2 Stop improvising clarification policy

Before asking clarifying questions for a likely route, call:

- `get_required_clarification_policy`

Use this tool when:

- the route is ambiguous
- required fields may be missing
- a route has a high correction or clarification history
- the routing summary indicates clarification-sensitive failure patterns

Required behavior:

- if the tool returns required missing fields, ask for them before committing to the route
- if it returns a recommended prompt shape, use that as the basis for the clarifying question
- if it indicates strong policy posture, prefer policy-driven clarification over freeform agent judgment

### 4.3 Route with historical outcome weighting

Before final route commitment for a materially ambiguous request, call:

- `get_outcome_weighted_routing_summary`

Use it to:

- compare candidate routes
- understand route success/failure history by request shape
- detect when a route looks attractive by similarity but performs poorly in outcomes

Required behavior:

- treat this as a route-bias correction layer
- do not use only lexical or local heuristic confidence if the summary shows repeated outcome failure for that route shape
- when the summary is sparse, fall back to existing heuristics rather than fabricating confidence

### 4.4 Add convergence interventions to loop handling

When a run shows repeated validator failures, repeated retries, or cycling behavior, call:

- `get_convergence_recommendation_summary`

Use it to decide whether to:

- continue retrying
- ask for clarification
- switch route
- escalate review
- tighten evidence requirements

Required behavior:

- stop treating repeated failure as only a local retry problem
- consult historical convergence patterns before re-running the same plan
- surface the recommendation into the orchestrator's retry controller or verifier policy

### 4.5 Use failure-mode playbooks instead of ad hoc loop fixes

When the workflow produces repeated failure signatures, call:

- `get_failure_mode_playbooks`

Use it when:

- the same validator fails across attempts
- similar findings repeat across runs
- the current run resembles a known error pattern

Required behavior:

- map repeated signatures to normalized next steps
- prefer returned playbook actions over ad hoc "try again" behavior
- log when a playbook was applied so future analysis can explain the intervention

### 4.6 Make adaptation actor-aware

When the actor is known and historical data exists, call:

- `get_actor_adaptation_summary`

Use it to adjust:

- how much clarification to ask for up front
- how aggressively to trust initial route selection
- whether to bias toward stricter validation or earlier clarification

Required behavior:

- apply this as a posture adjustment, not as a hard override
- if the actor has no history, degrade gracefully to the default flow
- do not invent actor-specific policy if the tool returns sparse data

### 4.7 Respect governance rollout posture

Before enabling stronger policy-driven behavior broadly, call:

- `get_policy_governance_rollout_summary`

Use it to decide:

- whether a policy looks ready for broader use
- whether a policy should remain limited to observation or selective rollout
- whether drift or suppression patterns suggest caution

Required behavior:

- do not assume every learned policy should be applied globally
- use the governance summary as the guardrail between observation and promotion

---

## 5. Recommended Call Pattern

This is the recommended runtime sequence for a non-trivial routed request.

### Step 1. Initial triage lookup

Call:

- `triage_request_with_memory`

Pass:

- repository identity
- request text
- any planning context you already have
- `actor_email` when available

Read from the response:

- candidate routing guidance
- similarity-backed triage memory
- embedded adaptive fields such as:
  - `outcome_weighted_routes`
  - `required_clarification_policy`
  - `requires_clarification_recommendation`
  - `actor_adaptation`

### Step 2. Resolve ambiguity with explicit policy reads

If the request is ambiguous or high-stakes, explicitly read:

- `get_outcome_weighted_routing_summary`
- `get_required_clarification_policy`
- `get_actor_adaptation_summary`

Reason:

- `triage_request_with_memory` can provide embedded guidance
- the dedicated tools let the orchestrator deepen or confirm those recommendations when the decision is consequential

### Step 3. Choose a route

Choose the route using a combination of:

- current request understanding
- prior similar cases
- outcome-weighted route quality
- clarification requirements
- actor posture

Do not choose the route from similarity alone.

### Step 4. Ask clarifying questions if policy requires it

If required clarification fields are missing:

- ask them before hard route commitment or before expensive workflow execution

If the policy returns only a recommendation:

- weigh it against current confidence and route risk

### Step 5. Execute workflow and persist facts

During execution, continue writing:

- `save_workflow_run`
- `save_workflow_phase_state`
- `save_workflow_validator_result`
- `save_workflow_finding`
- `save_workflow_finding_decision`

Without these writes, convergence and playbook tools will degrade in quality.

### Step 6. Intervene when the run drifts

If the run loops, stalls, or accumulates repeated failures, read:

- `get_convergence_recommendation_summary`
- `get_failure_mode_playbooks`

Apply the recommended intervention before repeating the same retry cycle.

### Step 7. Close the triage feedback loop

At the end of the workflow, call:

- `finalize_triage_outcome`

This keeps the memory and policy layer learning from real outcomes.

---

## 6. Minimum Behavioral Contract For `mcp-agents-workflow`

To claim V4 integration, `mcp-agents-workflow` should satisfy all of the following.

### Required

- It passes `actor_email` when known.
- It uses `get_required_clarification_policy` before freeform clarification on ambiguous or policy-sensitive routes.
- It uses `get_outcome_weighted_routing_summary` before route commitment on materially ambiguous requests.
- It consults `get_convergence_recommendation_summary` when retries or validator failures repeat.
- It consults `get_failure_mode_playbooks` for repeated signatures instead of only retrying locally.
- It uses `get_policy_governance_rollout_summary` before broad policy promotion behavior.
- It finalizes outcomes so routing and clarification policies continue learning.

### Strongly recommended

- It reads `get_actor_adaptation_summary` when actor identity is available and the request matters enough for adaptive posture.
- It records, in its own run reasoning, when a returned playbook or convergence recommendation changed behavior.

---

## 7. Fallback Behavior

The external orchestrator must degrade safely.

### If a V4 tool returns sparse or empty data

- fall back to the existing route/clarification logic
- do not fabricate certainty from empty guidance

### If the server is healthy but not ready

- do not proceed with write-heavy workflow assumptions
- surface dependency readiness failure clearly

### If remote write guards reject a write

- surface the guard failure explicitly
- do not silently retry indefinitely

### If actor identity is missing

- continue without actor adaptation
- do not block the request only because `actor_email` is absent

---

## 8. Suggested Implementation Order In `mcp-agents-workflow`

Implement in this order to keep risk controlled.

1. Thread `actor_email` through the relevant triage and workflow entrypoints.
2. Update route-selection logic to consult `get_outcome_weighted_routing_summary`.
3. Update clarification generation to consult `get_required_clarification_policy`.
4. Update retry/loop handling to consult `get_convergence_recommendation_summary`.
5. Update repeated-failure handling to consult `get_failure_mode_playbooks`.
6. Add `get_actor_adaptation_summary` as a posture-adjustment layer.
7. Add `get_policy_governance_rollout_summary` to any policy-promotion or selective rollout logic.
8. Confirm `finalize_triage_outcome` is always called at workflow closeout.

This order gives value early while avoiding a large all-at-once orchestration rewrite.

---

## 9. Smoke Checks After Integration

After updating `mcp-agents-workflow`, confirm all of the following.

### Triage path

- a request with a known actor passes `actor_email`
- an ambiguous request triggers clarification-policy lookup
- a multi-route request triggers outcome-weighted routing lookup

### Workflow loop path

- repeated validator failures trigger convergence-summary lookup
- repeated failure signatures trigger playbook lookup

### Closeout path

- completed runs finalize triage outcomes

### Safety path

- empty or sparse V4 responses fall back cleanly
- write guard failures are surfaced, not swallowed

---

## 10. What Not To Do

- Do not duplicate the policy synthesis logic in `mcp-agents-workflow`.
- Do not infer that every policy recommendation is mandatory unless the returned policy indicates that.
- Do not use actor adaptation as a hard per-user rule engine.
- Do not keep retrying a failing route without checking convergence and playbook guidance once repeated failures appear.
- Do not skip outcome finalization, or the learning loop will weaken over time.

---

## 11. Practical Summary

Before this integration, `mcp-agents-workflow` mostly used `memory-knowledge` as storage and retrieval.

After this integration, it should also use `memory-knowledge` as:

- a route-quality advisor
- a clarification-policy advisor
- a convergence advisor
- a failure-playbook advisor
- an actor-adaptation advisor
- a governance advisor

That is the actual V4 upgrade.
