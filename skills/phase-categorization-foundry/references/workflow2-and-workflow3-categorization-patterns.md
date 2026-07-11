# Workflow 2 And Workflow 3 Phase 1 Categorization Patterns

This reference records the current repo patterns for phase-owned categorization contracts. Use it as grounding when creating or auditing a new non-mechanical workflow phase.

## Source Files To Inspect

- Software constitution: `software company workflows/Software Delivery Workflow Constitution.md`
- Executable Workflow 2 YAML: `src/workflow_orch/workflows/requirements-hardening-precode-workflow.yaml`
- Executable Workflow 3 YAML: `src/workflow_orch/workflows/acceptance-requirements-precode-workflow.yaml`
- Package enum contracts: `src/workflow_orch/contracts/enums/`
- Software-folder enum mirrors: `software company workflows/enums/`
- Manager/parser/composer: `src/workflow_orch/phase_ledger_manager.py`
- Prompt injection: `src/workflow_orch/workflow_engine.py`
- Manager snapshot output routing: `src/workflow_orch/workflow_ledger_manager.py`
- Personas: `src/agents/*`
- Tests: `tests/test_contracts.py`, `tests/test_phase_ledger_loop_executor.py`, `tests/test_phase_ledger_manager.py`, `tests/test_agents.py`

Use the software constitution to determine the workflow and phase purpose. Use YAML to verify executable wiring. If the constitution says the phase consumes or produces something different from YAML, report that mismatch before designing or auditing categories.

## Contract File Shape

Record-type enum contracts are JSON objects:

```json
{
  "name": "Human Name",
  "contract_key": "snake_case_contract_key",
  "values": [
    "VALUE_ONE",
    "COVERAGE_ONLY"
  ]
}
```

Workflow 3 Phase 1 also uses a `descriptions` object because the atomizer maps upstream packet types into acceptance input categories:

```json
{
  "values": ["ACCEPTANCE_INPUT", "RESIDUAL_RISK", "UNANSWERED_QUESTION", "READINESS", "COVERAGE_ONLY"],
  "descriptions": {
    "ACCEPTANCE_INPUT": "A source-stated hardened requirement, rule, behavior, constraint, or obligation that must be considered when defining acceptance expectations and definition-of-done criteria."
  }
}
```

Descriptions are useful when the producer must map source packet categories into new phase-owned categories. They are not required for simple two-or-three-value contracts.

## Workflow 2 Phase Categorization Map

Workflow 2 is `requirements-hardening-precode-workflow`.

### Phase 1: atomize-requirements

Purpose: break triage handoff into primitive requirement statements.

Current state: legacy atomizer surface. It emits primitive requirements but does not use a phase-owned categorization enum in the same way as later phases. Do not use this as the preferred categorization integration template. Use Workflow 3 Phase 1 for atomizer categorization.

### Phase 2: distill-stated-constraints

Purpose from YAML: identify explicit limits, exclusions, boundaries, and hard rules stated in primitive requirements.

Contract: `requirements-precode-stated-constraint-record-type.json`

Values:

- `STATED_CONSTRAINT`
- `PRESERVATION_CONSTRAINT`
- `COVERAGE_ONLY`

Why the categories fit:

- `STATED_CONSTRAINT` captures explicit prohibitions, exclusions, scope boundaries, authority rules, uniqueness rules, and cardinality rules.
- `PRESERVATION_CONSTRAINT` captures source text requiring existing behavior or scope to remain unchanged.
- `COVERAGE_ONLY` preserves source text that does not explicitly state a constraint.

Persona pattern:

- Producer starts every `detail` with one prefix from the contract.
- Verifier flags invalid prefix, allowed behavior mislabeled as constraint, and `COVERAGE_ONLY` when the source explicitly states a constraint.
- Critic repairs accepted findings using only valid prefixes and does not remove `COVERAGE_ONLY` only because it is omitted downstream.

Manager pattern:

- Loads `STATED_CONSTRAINT_RECORD_TYPE_VALUES` and ordered values from the contract.
- Uses `require_contract_value` for `STATED_CONSTRAINT`, `PRESERVATION_CONSTRAINT`, and `COVERAGE_ONLY`.
- Parses details by iterating ordered values and requiring `"<VALUE>: <text>"`.
- Adds duplicate/detail contract findings and composes output under `requirements_precode.constraints`.

### Phase 3: identify-requirement-ambiguities

Purpose from YAML: identify primitive requirements whose meaning can reasonably be interpreted in more than one way.

Contract: `requirements-precode-requirement-ambiguity-record-type.json`

Values:

- `BEHAVIOR_AMBIGUITY`
- `SCOPE_AMBIGUITY`
- `COVERAGE_ONLY`

Why the categories fit:

- `BEHAVIOR_AMBIGUITY` captures unclear action, permission, state change, flow, or behavior.
- `SCOPE_AMBIGUITY` captures unclear role, account, company, user, surface, record, or data scope boundary.
- `COVERAGE_ONLY` preserves source text that does not state a behavior or scope ambiguity.

Persona pattern:

- Producer makes one ambiguity per record and chooses behavior versus scope based on source text.
- Verifier flags invalid prefix and `COVERAGE_ONLY` when the source states a behavior or scope ambiguity.
- Critic repairs accepted findings using contract prefixes and rejects findings already covered by another ambiguity record.

Manager pattern:

- Loads `REQUIREMENT_AMBIGUITY_RECORD_TYPE_VALUES` and ordered values from the contract.
- Uses `require_contract_value` for `BEHAVIOR_AMBIGUITY`, `SCOPE_AMBIGUITY`, and `COVERAGE_ONLY`.
- Parses details by iterating ordered values.
- Adds duplicate/detail findings and composes output under `requirements_precode.ambiguities`.

### Phase 4: identify-missing-requirement-decisions

Purpose from YAML: identify decisions required before implementation that are not stated by primitive requirements, constraints, or ambiguity records.

Contract: `requirements-precode-missing-requirement-decision-record-type.json`

Values:

- `BEHAVIOR_DECISION`
- `SCOPE_DECISION`
- `COVERAGE_ONLY`

Why the categories fit:

- `BEHAVIOR_DECISION` captures a missing decision about what the system should do, allow, deny, trigger, persist, recover, notify, validate, or execute.
- `SCOPE_DECISION` captures a missing decision about which roles, records, fields, companies, users, pages, APIs, states, or data are included or excluded.
- `COVERAGE_ONLY` preserves source text that does not require a missing behavior or scope decision.

Persona pattern:

- Producer emits a missing decision only when a product behavior or scope choice is needed before implementation.
- Verifier flags implementation-only questions and details that restate the requirement instead of naming the missing decision.
- Critic converts implementation-only findings to `COVERAGE_ONLY` when the source still needs coverage.

Manager pattern:

- Loads `MISSING_REQUIREMENT_DECISION_RECORD_TYPE_VALUES` and ordered values from the contract.
- Uses `require_contract_value` for `BEHAVIOR_DECISION`, `SCOPE_DECISION`, and `COVERAGE_ONLY`.
- Parses details by iterating ordered values.
- Adds duplicate/detail findings and composes output under `requirements_precode.missing_decisions`.

### Phase 5: convert-hardening-gaps-into-questions

Purpose from YAML: convert unresolved pre-code requirements meaning-hardening gaps from primitive requirements, stated constraints, ambiguities, missing decisions, and feedback into concrete requester questions.

Contract: `requirements-precode-hardening-question-record-type.json`

Values:

- `QUESTION`
- `COVERAGE_ONLY`

Why the categories fit:

- `QUESTION` is the only emitted substantive category because the phase's job is question production.
- `COVERAGE_ONLY` preserves subscribed source text that does not need a question.

Persona pattern:

- Producer uses only record types from the injected contract.
- Verifier requires `QUESTION` to be one concrete operator-answerable question ending with `?`, not a question about whether the gap exists.
- Critic repairs accepted invalid question or coverage use with valid `HQ-*` records.

Manager pattern:

- Loads `HARDENING_QUESTION_RECORD_TYPE_VALUES` and ordered values from the contract.
- Uses `require_contract_value` for `QUESTION` and `COVERAGE_ONLY`.
- Parses details by iterating ordered values and validates non-empty text.
- Adds duplicate/detail findings and composes output under `requirements_precode.questions`, suppressing `COVERAGE_ONLY`.

### Phase 6: persist-requirements-hardening-feedback

Purpose: mechanical storage of question/answer feedback.

Current state: `feedback_persistence`, not a phase-ledger-loop producer phase. It does not need a phase categorization enum.

### Phase 7: compose-hardened-requirements-packet

Purpose from YAML: compose the hardened pre-code requirements packet from primitive requirements, constraints, ambiguities, missing decisions, questions, and feedback.

Top-level contract: `requirements-precode-hardened-packet-record-type.json`

Values:

- `HARDENED_REQUIREMENT`
- `RESIDUAL_RISK`
- `READINESS`
- `COVERAGE_ONLY`

Nested readiness contract: `requirements-precode-hardened-packet-readiness.json`

Values:

- `READY_FOR_TESTING_REQUIREMENTS`
- `NEEDS_MORE_FEEDBACK`
- `PROCEED_WITH_RESIDUAL_RISK`

Nested residual-risk contract: `requirements-precode-hardened-packet-residual-risk-type.json`

Values:

- `UNRESOLVED_AMBIGUITY`
- `UNRESOLVED_DECISION`
- `UNANSWERED_QUESTION`

Why the categories fit:

- `HARDENED_REQUIREMENT` carries final downstream-ready requirement sentences.
- `RESIDUAL_RISK` carries unresolved ambiguity, decision, or unanswered question risk that must remain visible.
- `READINESS` states the packet's handoff status exactly once.
- `COVERAGE_ONLY` preserves source text needed for full reconstruction but not emitted packet output.

Persona pattern:

- Producer emits readiness exactly once using the readiness contract.
- Verifier checks record prefix, readiness value, residual-risk type, exactly one readiness, and readiness/risk consistency.
- Critic repairs accepted findings using only valid packet, readiness, and residual-risk values.

Manager pattern:

- Loads top-level packet, readiness, and residual-risk values from JSON contracts.
- Uses `require_contract_value` for key named values.
- Parser validates:
  - `READINESS: <READINESS_VALUE>`
  - `RESIDUAL_RISK: <RESIDUAL_RISK_TYPE>: <text>`
  - non-empty text after every prefix.
- Shape contract validates readiness count and readiness/risk consistency.
- Composer emits packet output under `requirements_precode.hardened_packet`, suppressing `COVERAGE_ONLY`.

## Workflow 3 Phase 1 Categorization Pattern

Workflow 3 is `acceptance-requirements-precode-workflow`.

### Phase 1: atomize-requirements

Purpose from YAML: break the hardened requirements packet into primitive acceptance input statements so later phases reason over one behavior or rule at a time.

Contract: `acceptance-precode-primitive-input-record-type.json`

Values:

- `ACCEPTANCE_INPUT`
- `RESIDUAL_RISK`
- `UNANSWERED_QUESTION`
- `READINESS`
- `COVERAGE_ONLY`

Descriptions:

- `ACCEPTANCE_INPUT`: source-stated hardened requirement, rule, behavior, constraint, or obligation for acceptance expectations and definition-of-done criteria.
- `RESIDUAL_RISK`: source-stated risk carried forward from requirements hardening.
- `UNANSWERED_QUESTION`: source-stated open question or unresolved decision from the hardened packet.
- `READINESS`: source-stated readiness or handoff status.
- `COVERAGE_ONLY`: source text that must be covered but is not one of the meaningful packet item types.

Why the categories fit:

- The phase consumes Workflow 2's final packet, not raw requirements.
- The source packet can contain final requirements, residual risks, unanswered questions, and readiness status.
- Downstream acceptance phases need those packet item types preserved instead of flattening everything into an acceptance requirement.

Persona integration:

- Producer says each detail must start with one allowed prefix from the injected contract, followed by `: ` and one packet item.
- Producer says the injected values and descriptions are the only classification contract.
- Verifier flags invalid prefixes and prefix/source mismatches.
- Verifier flags `COVERAGE_ONLY` when the source states a hardened requirement, residual risk, unanswered question, or readiness statement.
- Critic repairs accepted findings with one allowed detail prefix from the injected contract.

Manager integration:

- Loads `ACCEPTANCE_PRIMITIVE_INPUT_RECORD_TYPE_VALUES` with `load_enum_contract`.
- Loads ordered values with `load_json_contract(...)[\"values\"]`.
- Uses `require_contract_value` for:
  - `ACCEPTANCE_INPUT`
  - `RESIDUAL_RISK`
  - `UNANSWERED_QUESTION`
  - `READINESS`
  - `COVERAGE_ONLY`
- Uses `acceptance_atomized_input_detail_contract_report`.
- Uses `_parse_acceptance_atomized_input_detail`, which iterates ordered values and requires `\"<VALUE>: <text>\"`.
- Uses `acceptance_atomized_input_duplicate_pair_report`.
- Uses `append_acceptance_atomized_input_duplicate_findings`.
- Routes manager checks by output context key `acceptance_precode.primitive_requirements`.
- Composes manager output with `compose_acceptance_atomized_input_phase_output_text`.
- Routes manager snapshot hydration for `acceptance_precode.primitive_requirements`.

Prompt injection:

- In `workflow_engine.py`, injection is guarded by both:
  - `phase.id == \"atomize-requirements\"`
  - `phase.phase_ledger_loop.output.context_key == \"acceptance_precode.primitive_requirements\"`
- This guard matters because Workflow 2 also has `atomize-requirements`; phase id alone is not enough when ids are reused across workflows.
- The prompt includes the full JSON contract, not only the values array, because descriptions are part of the contract.

Preferred atomizer rule:

- For atomizer phases that consume a final packet or mixed handoff, use Workflow 3 Phase 1 as the integration template.
- Do not copy Workflow 2 Phase 1 as a categorization template because it is a legacy primitive requirement atomizer without a phase-owned enum contract.

## Manager Integration Pattern

A phase categorization contract is properly integrated into manager code when all of these are true:

- The contract file exists in the package enum directory.
- The mirrored contract exists in the software-folder enum directory.
- Ordered values are loaded from JSON rather than duplicated as a private list.
- Required branch values are checked with `require_contract_value`.
- Detail parsing loops through ordered values and requires `VALUE: text`.
- Detail-contract reports use the phase parser.
- Duplicate reports use phase-owned functions and labels.
- Manager verifier findings use phase-owned operation names.
- Output composition uses phase-owned parser and labels.
- `COVERAGE_ONLY` is suppressed only when the downstream text output should omit it.
- Packet phases validate nested contracts and shape rules when applicable.

## Prompt Injection Pattern

Prompt injection is properly integrated when:

- The prompt includes the exact enum filename.
- The JSON payload comes from `load_json_contract` or values loaded from the same JSON contract.
- The injection is guarded tightly enough to avoid cross-workflow phase-id collisions.
- The mechanical prefix rule is included once.
- Tests assert the expected contract filename and representative values appear in the prompt.

## Persona Integration Pattern

Personas are properly integrated when:

- Producer names the injected contract as the only category source.
- Producer uses values for phase-specific decisions only after exact text is approved.
- Verifier flags invalid prefixes and category/source mismatches.
- Critic repairs accepted findings using only valid categories.
- No persona references enum filenames from another phase.
- No persona lists old values from a cloned phase unless those exact values are still the approved contract.

Do not add or revise phase-specific persona text without exact user approval.

## Category Quality Checklist

A good category set is:

- Grounded in the executable phase purpose.
- Needed by a downstream subscriber, final handoff, manager composer, or verifier decision.
- Small enough that a producer can choose the category reliably.
- Mutually exclusive at the top level.
- Not a restatement of examples from one prompt.
- Not an implementation mechanism unless the phase is explicitly code-contextual.
- Supported by manager prefix validation.
- Supported by persona rules without creating a semantic loop.

## Red Flags

- Category values copied from a cloned source phase whose purpose differs.
- A category named after a downstream prose heading instead of a producer decision.
- Missing `COVERAGE_ONLY` in a full-universe or full-reconstruction phase.
- Prompt injection keyed only by phase id when multiple workflows reuse the same phase id.
- Manager parser with a private hardcoded list instead of contract-loaded ordered values.
- Persona text that names allowed values but does not reference the injected contract.
- Verifier rules that require nuanced semantic judgments the manager already owns mechanically.
- Critic rules that preserve or remove records in ways that fight manager coverage findings.
