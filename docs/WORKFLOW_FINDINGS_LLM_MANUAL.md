# Workflow Findings Integration Manual
## For LLMs Integrating With `memory-knowledge`

**Audience:** an external LLM or agent framework that needs to write and read structured workflow findings, critic decisions, suppressions, and finding analytics  
**Status:** implemented, deployed, and live  
**Server:** `memory-knowledge` MCP server

---

## 1. What This Upgrade Added

This upgrade added a first-class workflow-finding layer on top of the existing workflow-run telemetry.

The server now supports:

- structured finding persistence
- structured critic-decision persistence
- same-run suppression lookup for later verifier/reviewer rounds
- repeated-finding analytics
- agent failure-mode analytics

The main purpose is to let an external workflow system persist reviewer/verifier output as structured data instead of only markdown artifacts.

This is now live in the `memory-knowledge` server and remote database.

---

## 2. What The Integrator Owns

This repo owns:

- the database schema
- the MCP tools
- the storage contracts
- the analytics/query behavior

The external workflow/orchestrator LLM owns:

- when findings are emitted
- how fingerprints are generated
- when critic decisions are written
- when suppression lookup is consulted
- how workflow phases map to your verifier/reviewer/critic loop

Important:

- this server does **not** infer findings from markdown
- this server does **not** auto-observe your workflow engine
- if you do not call the write tools, the analytics layer stays empty

---

## 3. Mental Model

The relevant hierarchy is:

- `workflow run`
  - `finding`
    - `critic decision`

More precisely:

- a workflow run belongs to one repository
- a finding belongs to one run, one phase, one attempt, and one fingerprint
- a critic decision belongs to one finding
- decisions are append-only history
- suppression lookup returns the latest eligible decision state for matching findings in the same run

---

## 4. Canonical Stored Values

Use codes, not labels.

### 4.1 Finding kind codes

- `HALLUCINATED_REFERENCE`
- `FALSE_POSITIVE`
- `MISSING_REQUIREMENT`
- `LOGIC_GAP`
- `DUPLICATE`
- `UNVERIFIABLE`
- `LOW_PRIORITY_IMPROVEMENT`
- `SCOPE_LEAK`
- `UNKNOWN`

Default if omitted:

- `UNKNOWN`

### 4.2 Finding status codes

- `OPEN`
- `RESOLVED`
- `SUPPRESSED`

Default if omitted:

- `OPEN`

### 4.3 Decision bucket codes

- `FIX_NOW`
- `FIX_NOW_PROMOTED`
- `VALID`
- `ACKNOWLEDGE_OK`
- `DISMISS`
- `FILTERED`

### 4.4 Suppression scope codes

Currently only:

- `RUN_LOCAL`

Default if omitted:

- `RUN_LOCAL`

---

## 5. Tool Names

Inside an agent framework using the MCP namespace, these appear as:

- `mcp__memory-knowledge__save_workflow_finding`
- `mcp__memory-knowledge__save_workflow_finding_decision`
- `mcp__memory-knowledge__list_workflow_finding_suppressions`
- `mcp__memory-knowledge__get_finding_pattern_summary`
- `mcp__memory-knowledge__get_agent_failure_mode_summary`
- `mcp__memory-knowledge__list_reference_values`
- `mcp__memory-knowledge__save_workflow_run`
- `mcp__memory-knowledge__get_workflow_run`

If you are calling the raw HTTP MCP endpoint directly, use the unprefixed tool names:

- `save_workflow_finding`
- `save_workflow_finding_decision`
- `list_workflow_finding_suppressions`
- `get_finding_pattern_summary`
- `get_agent_failure_mode_summary`

---

## 6. Required Integration Sequence

The correct lifecycle is:

1. persist the workflow run
2. persist any phase state you want tracked
3. persist findings emitted by verifier/reviewer steps
4. persist critic decisions about those findings
5. query suppressions before rerunning later verifier/reviewer rounds in the same run
6. query analytics for reporting, tuning, or learning

Do not start with findings before the run exists.

---

## 7. Write Tool: `save_workflow_finding`

### Required inputs

- `repository_key`
- `run_id`
- `workflow_name`
- `phase_id`
- `agent_name`
- `attempt_number`
- `finding_fingerprint`
- `finding_title`
- `finding_message`

### Optional inputs

- `artifact_name`
- `artifact_iteration`
- `artifact_hash`
- `location`
- `evidence_text`
- `finding_kind_code`
- `severity`
- `source_kind`
- `status_code`
- `actor_email`
- `context_json`
- `correlation_id`

### Server behavior

- resolves repository and run
- rejects if the run does not belong to that repository
- rejects if `workflow_name` does not match the canonical run workflow
- rejects empty `phase_id`
- rejects empty `finding_fingerprint`
- rejects `attempt_number < 1`
- validates reference codes
- defaults `finding_kind_code` to `UNKNOWN`
- defaults `status_code` to `OPEN`
- upserts by:
  - `(workflow_run_id, phase_id, attempt_number, finding_fingerprint)`

That means:

- writing the same finding key again updates the existing finding row
- writing the same fingerprint in a later attempt creates a new finding row because `attempt_number` changed

### Intended fingerprint rule

You should generate a fingerprint that stays stable for the same logical finding inside a phase/attempt.

Good inputs to fingerprint:

- phase id
- normalized location
- normalized finding title/type
- a stable logical signature, not raw prose alone

Do not use timestamps in the finding fingerprint.

### Example payload

```json
{
  "repository_key": "payments-api",
  "run_id": "8f9d6b3f-7a7c-4fd7-9da2-1e4eaf9b4df4",
  "workflow_name": "verify-plan",
  "phase_id": "verifier",
  "agent_name": "VerifierAgent",
  "attempt_number": 1,
  "finding_fingerprint": "plan:review-loop:missing-critic-stage",
  "finding_title": "Critic stage missing from loop",
  "finding_message": "The plan runs repeated verifier passes but does not include the critic stage required by the workflow.",
  "finding_kind_code": "MISSING_REQUIREMENT",
  "location": "Tasks/foo/plan.md:88",
  "evidence_text": "Plan describes verifier reruns only.",
  "actor_email": "user@company.com",
  "context_json": {
    "loop": "verify-plan",
    "source": "verifier"
  }
}
```

---

## 8. Write Tool: `save_workflow_finding_decision`

### Purpose

Persist one critic decision about one existing finding.

### Required inputs

- `repository_key`
- `run_id`
- `workflow_name`
- `critic_phase_id`
- `critic_agent_name`
- `attempt_number`
- `finding_fingerprint`
- `decision_bucket_code`
- `actionable`
- `suppress_on_rerun`

### Optional inputs

- `reason_text`
- `evidence_text`
- `suppression_scope_code`
- `finding_phase_id`
- `artifact_name`
- `artifact_iteration`
- `artifact_hash`
- `actor_email`
- `context_json`
- `created_utc`
- `correlation_id`

### Resolution behavior

The server resolves the target finding by:

- `run_id`
- `attempt_number`
- `finding_fingerprint`
- optional `finding_phase_id`

If multiple findings match and `finding_phase_id` is missing, the server returns an error asking for `finding_phase_id`.

### History behavior

Critic decisions are append-only.

This is deliberate:

- do not expect old decisions to be overwritten
- a revised critic decision should be recorded as a new row

### Duplicate behavior

The server rejects only exact duplicate inserts for the same:

- finding
- critic phase
- critic agent
- attempt
- decision bucket
- `created_utc`

If you omit `created_utc`, the server uses `NOW()`, which means the write is treated as a new history row.

That is intentional.

### Suppression rule

If you want a decision to be available through suppression lookup, set:

- `suppress_on_rerun = true`

and use an eligible bucket:

- `ACKNOWLEDGE_OK`
- `DISMISS`
- `FILTERED`

Do not assume `VALID` or `FIX_NOW` decisions will appear in suppression lookup.

### Example payload

```json
{
  "repository_key": "payments-api",
  "run_id": "8f9d6b3f-7a7c-4fd7-9da2-1e4eaf9b4df4",
  "workflow_name": "verify-plan",
  "critic_phase_id": "critic",
  "critic_agent_name": "CriticAgent",
  "attempt_number": 1,
  "finding_fingerprint": "plan:review-loop:missing-critic-stage",
  "decision_bucket_code": "FIX_NOW",
  "actionable": true,
  "suppress_on_rerun": false,
  "reason_text": "This is a direct contract violation in the plan.",
  "evidence_text": "The verify-plan skill requires verifier plus critic, not verifier-only reruns.",
  "actor_email": "user@company.com"
}
```

---

## 9. Read Tool: `list_workflow_finding_suppressions`

### Purpose

Return suppressible findings for the same run so later verifier/reviewer rounds can ignore already-dismissed or locally-acknowledged items.

### Required inputs

- `repository_key`
- `run_id`
- `workflow_name`
- `phase_id`

### Optional inputs

- `artifact_name`
- `artifact_iteration`
- `artifact_hash`
- `limit`
- `correlation_id`

### Actual selection logic

The tool returns the latest matching decision state per fingerprint within the same run and phase, but only when:

- `suppress_on_rerun = true`
- decision bucket is one of:
  - `ACKNOWLEDGE_OK`
  - `DISMISS`
  - `FILTERED`

### Intended usage

Call this before a later verifier/reviewer attempt in the same run and use the returned fingerprints to suppress repeated findings.

### Example usage pattern

1. Attempt 1 verifier writes findings
2. Critic writes decisions
3. Before attempt 2 verifier runs, call `list_workflow_finding_suppressions`
4. The orchestrator passes those fingerprints into the verifier prompt or filtering logic

### Example result shape

The tool returns a normal `WorkflowResult` with `data.items`.

Each item includes fields like:

- `finding_fingerprint`
- `finding_title`
- `location`
- `decision_bucket`
- `reason_text`
- `suppress_on_rerun`
- artifact identity fields
- `created_utc`

---

## 10. Analytics Tool: `get_finding_pattern_summary`

### Purpose

Return grouped repeated-finding patterns over persisted findings.

### Filters

- `repository_key` required
- `workflow_name` optional
- `phase_id` optional
- `agent_name` optional
- `finding_kind_code` optional
- `since_utc` optional
- `until_utc` optional
- `limit` optional

### What it summarizes

This is a latest-state summary over findings, not an all-events history rollup.

Important:

- it uses the latest decision state per finding row
- it groups by:
  - repository
  - workflow
  - finding kind
  - phase

### What to use it for

- repeated requirement gaps
- repeated hallucination patterns
- repeated logic-gap patterns by phase
- trend reporting

### Zero-match behavior

Zero-match queries return success with:

- `summary: []`
- `eligible_run_count: 0`
- `excluded_run_count: 0`

Do not treat that as an error.

---

## 11. Analytics Tool: `get_agent_failure_mode_summary`

### Purpose

Return grouped failure-mode patterns by stored `agent_name`.

### Filters

- `repository_key` required
- `workflow_name` optional
- `phase_id` optional
- `agent_name` optional
- `since_utc` optional
- `until_utc` optional
- `limit` optional

### What it groups by

- repository
- workflow
- agent
- finding kind
- phase

### What it reports

Typical row fields include:

- `finding_count`
- `distinct_fingerprint_count`
- `dismiss_count`
- `acknowledge_count`
- `fix_now_count`
- `critic_dismiss_rate`
- `critic_actionable_rate`
- `repeat_rate`
- `top_examples`

### Intended use

Use this when you want to know:

- which agent roles produce repeated hallucinations
- which agent roles repeatedly miss requirements
- where critic actionability remains high

This is the right summary for agent-attributed quality, not `get_finding_pattern_summary`.

---

## 12. How To Integrate In A Real Review Loop

For a verifier/critic loop, the recommended pattern is:

1. `save_workflow_run`
2. optional `save_workflow_phase_state` for verifier start
3. for each verifier/reviewer finding:
   - `save_workflow_finding`
4. for each critic judgment:
   - `save_workflow_finding_decision`
5. before the next verifier/reviewer retry in the same run:
   - `list_workflow_finding_suppressions`
6. after runs accumulate:
   - `get_finding_pattern_summary`
   - `get_agent_failure_mode_summary`

If you also use the broader telemetry stack, keep writing:

- `save_workflow_phase_state`
- `save_workflow_validator_result`

Those remain important for the other analytics tools.

---

## 13. Error Handling Rules

Treat these as expected contract failures, not transport failures:

- repository not found
- invalid `run_id`
- run/repository mismatch
- `workflow_name` mismatch
- empty `phase_id`
- empty `finding_fingerprint`
- invalid reference code
- ambiguous finding resolution for decision writes
- invalid JSON in `context_json`
- invalid ISO-8601 timestamp in `created_utc`, `since_utc`, or `until_utc`
- `limit < 0`

Your integrator should surface the returned `WorkflowResult.error` clearly.

Do not retry those blindly.

---

## 14. Common Integrator Mistakes

Do not:

- write findings before the run exists
- use freeform labels instead of canonical codes
- use `attempt_number = 0`
- send empty `phase_id`
- assume decisions overwrite previous decisions
- assume suppression lookup includes every decision bucket
- treat empty analytics results as failures
- confuse `actor_email` with internal subagent identity

---

## 15. Minimal Example End-to-End

1. Persist run:

```json
{
  "repository_key": "payments-api",
  "run_id": "8f9d6b3f-7a7c-4fd7-9da2-1e4eaf9b4df4",
  "workflow_name": "verify-plan",
  "status_code": "RUN_RUNNING",
  "actor_email": "user@company.com"
}
```

2. Persist finding:

```json
{
  "repository_key": "payments-api",
  "run_id": "8f9d6b3f-7a7c-4fd7-9da2-1e4eaf9b4df4",
  "workflow_name": "verify-plan",
  "phase_id": "verifier",
  "agent_name": "VerifierAgent",
  "attempt_number": 1,
  "finding_fingerprint": "missing-critic-step",
  "finding_title": "Critic stage missing",
  "finding_message": "The loop omits the critic stage.",
  "finding_kind_code": "MISSING_REQUIREMENT"
}
```

3. Persist critic decision:

```json
{
  "repository_key": "payments-api",
  "run_id": "8f9d6b3f-7a7c-4fd7-9da2-1e4eaf9b4df4",
  "workflow_name": "verify-plan",
  "critic_phase_id": "critic",
  "critic_agent_name": "CriticAgent",
  "attempt_number": 1,
  "finding_fingerprint": "missing-critic-step",
  "decision_bucket_code": "FIX_NOW",
  "actionable": true,
  "suppress_on_rerun": false
}
```

4. Query suppressions before retry:

```json
{
  "repository_key": "payments-api",
  "run_id": "8f9d6b3f-7a7c-4fd7-9da2-1e4eaf9b4df4",
  "workflow_name": "verify-plan",
  "phase_id": "verifier"
}
```

5. Query pattern analytics later:

```json
{
  "repository_key": "payments-api",
  "workflow_name": "verify-plan",
  "limit": 20
}
```

---

## 16. Final Operating Rule

Treat `memory-knowledge` as the canonical persistence and analytics plane for workflow findings.

Your external LLM system should:

- generate the findings and decisions
- call these tools deliberately
- use the returned suppressions and summaries to improve later runs

It should not invent parallel storage for the same facts unless there is a very strong reason.
