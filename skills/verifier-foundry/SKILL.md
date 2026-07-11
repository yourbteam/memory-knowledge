---
name: verifier-foundry
description: Use when creating or revising a workflow phase verifier persona. Enforces approval-gated, bounded verifier slices from the phase contract without adding producer, critic, manager, provider, model, or prompt-specific behavior.
---

# Verifier Foundry

Use this skill before creating or revising any phase-specific verifier persona.

The skill produces verifier slice text only. It does not write producer, critic, manager, canary, provider, model, or workflow YAML changes.

The skill has two modes:

- create a new verifier slice from a grounded phase contract;
- audit an existing verifier persona and identify whether it contains proven treatment that the foundry contract is missing.

## Baseline From Proven Verifiers

The common verifier baseline is limited to traits that appear across the proven Workflow 2 verifier pattern:

- strict JSON-array verifier findings through shared verifier slices;
- findings use exactly `id`, `reference_item_id`, `problem`, and `suggested_change_to`;
- verify required producer fields and strict JSON shape through shared slices;
- verify exact source quotes through shared slices;
- verify each detail is supported by its own `source_quote`;
- verify source coverage policy without taking over manager-owned coverage reconstruction;
- flag final `manager-gap-*` records through shared manager-gap handling;
- return `[]` when no real violation exists;
- flag only grounded violations in submitted producer output, source request, and phase contract;
- do not invent findings because output could be improved.

Do not treat an existing verifier persona as correct just because it passes this checklist. The checklist is a floor, not proof of quality.

## Grounding Rule

Ground the slice in current repo files before drafting:

- workflow YAML phase id and output context key;
- verifier shared slices already attached to the persona;
- producer enum contract JSON for the phase;
- source coverage mode;
- manager contract checks for the phase when they exist;
- producer phase-specific rules the verifier must mirror.

If any required fact is missing, stop and ask for that fact. Do not invent defaults.

## Existing Verifier Audit

When applying this skill to an existing verifier persona, do this before recommending changes:

1. List the current phase-specific verifier rules.
2. Map each rule to one of:
   - required by workflow YAML, enum contract, source coverage, producer rules, or manager checks;
   - approved phase-specific behavior;
   - unsupported role leakage or prompt-specific drift.
3. Identify any current rule that handles a real verifier problem better than this skill's baseline.
4. Report those as `verifier-foundry gaps` before proposing persona edits.

Do not call the skill complete if the existing persona contains useful grounded treatment that the skill would not know to ask about.

Promote an audit-discovered rule into the foundry only when it is a reusable verifier-construction rule, not merely wording that makes the audited persona pass. If it is phase-specific, keep it in the proposed verifier slice only.

## Required Inputs

Ask only for facts not already grounded in repo files or explicitly approved in the conversation:

- workflow name;
- phase id;
- phase job in one sentence;
- input source shape;
- source coverage mode;
- producer record ID prefix;
- enum contract file;
- allowed detail prefixes;
- what counts as a valid producer record;
- what counts as `COVERAGE_ONLY`;
- what must be flagged;
- what must not be flagged;
- duplicate rule;
- source reuse rule.

For multi-record-type phases, also require:

- the verifier rule for each meaningful enum value;
- the verifier rule for incorrect fallback use between enum values;
- source-stated record classes that must not be hidden as `COVERAGE_ONLY`;
- downstream artifact types that must be flagged if the producer creates them;
- the source quote granularity rule when one source span can contain multiple recordable items;
- the neutral text coverage rule for headings, labels, separators, connector text, transition text, and formatting text.

Do not ask for examples unless the user requests examples.

## Manager Contradiction Gate

Before drafting or auditing verifier text, compare it against manager behavior.

The verifier must not contradict these manager-owned decisions:

- exact source_quote presence is mechanically checked by the shared source-quote validation and manager findings;
- `full_universe_coverage` requires every non-separator source span to be covered at least once;
- whitespace-only and separator-only gaps are ignored by the manager;
- meaningful text after a separator is not ignored and may become `manager-gap-*`;
- repeated `source_quote` is allowed when repeated records have different details;
- same normalized `source_quote` array plus same normalized `detail` is a manager duplicate;
- final `manager-gap-*` records are invalid and must be flagged;
- verifier must not independently flag duplicated, overlapping, out-of-order, or uncovered reconstruction unless a `manager-gap-*` record or manager coverage finding is present;
- verifier must not suggest deleting `manager-gap-*` by itself when coverage mode requires the source span to remain covered;
- verifier must not flag `COVERAGE_ONLY` only because composed output hides it.

If a proposed verifier rule would make the critic remove an item that the manager will re-add, the rule is invalid.

## Verifier Flavors

Select exactly one flavor before drafting or auditing phase-specific text. If the phase does not fit one of these flavors, stop and ask for the intended verifier type.

### Phase 1 Atomizer Verifier

Use this flavor for the first phase of a workflow when the producer atomizes an input packet or prompt into primitive records for later phases.

Grounded traits from Workflow 2 Phase 1:

- evaluate atomization only where source text explicitly states splittable content;
- flag bundled producer details only when multiple explicit actionable items remain in one detail;
- flag a missing split only when the source explicitly names the item and no existing valid record carries it;
- allow repeated `source_quote` when repeated records carry different atomized details from the same source span;
- do not require splitting when the source states only one actionable item;
- do not require splitting implied, inferred, renamed, or absent items;
- do not re-flag a source span after all explicit items from that span are represented across separate records;
- for explicit equivalent labels, flag duplicate functional records only when the source states the equivalence.

For this flavor, require these inputs when missing:

- what counts as an atomized item for this workflow;
- producer ID prefix;
- whether explicit equivalence labels are in scope;
- source reuse rule.

### Classification Or Distillation Verifier

Use this flavor for phases like Workflow 2 Phases 2, 3, and 4, where the verifier checks one focused finding family over primitive records.

Grounded traits from Workflow 2 Phases 2-4:

- evaluate only source text that satisfies the phase category;
- flag producer details that describe a clear/non-category item as if it were a category finding;
- flag details that combine multiple category findings;
- flag missing category records only when the source explicitly contains the category finding and no existing valid record carries it;
- allow repeated `source_quote` when repeated records extract different single category findings from the same source span;
- flag detail prefixes that are not from the enum contract;
- flag a meaningful prefix when the text after it does not satisfy that prefix;
- flag `COVERAGE_ONLY` when the source_quote states a real category finding;
- do not infer category findings from what the source does not say;
- do not treat every requirement condition as the phase category;
- do not re-flag after all category findings from that source span are represented.

For this flavor, require these inputs when missing:

- exact category being verified;
- enum contract file and allowed prefixes;
- valid meaning for each meaningful prefix;
- explicit negative boundary;
- implementation-only boundary when relevant;
- duplicate/equivalence rule if labels or surfaces can represent the same thing.

### Questions Verifier

Use this flavor when the verifier checks operator-answerable questions generated from prior distilled gaps and feedback.

Grounded traits from Workflow 2 Phase 5:

- flag detail prefixes that are not from the question enum contract;
- flag a question that is not one concrete operator-answerable question ending with `?`;
- flag a question that asks whether the gap exists instead of asking for the missing answer needed to close the gap;
- flag a question already answered by feedback;
- flag a question not backed by an unresolved upstream gap section;
- flag implementation, codebase, file, API, test, or repository questions unless the phase is explicitly code-aware;
- flag duplicate questions that ask for the same needed answer;
- flag `COVERAGE_ONLY` when the source text shows an unresolved upstream gap that needs a question;
- do not require questions for source text already answered by feedback;
- do not flag `COVERAGE_ONLY` only because it is not emitted downstream.

For this flavor, require these inputs when missing:

- which upstream gap sections can require questions;
- which source section contains feedback;
- question enum contract file;
- duplicate-question rule.

### Handoff Packet Distiller Verifier

Use this flavor when the verifier checks a final handoff packet for the next workflow.

Grounded traits from Workflow 2 Phase 7:

- flag detail prefixes that are not from the packet enum contract;
- flag final requirement records that are not downstream-ready requirement sentences;
- enforce exactly one readiness record when the packet contract requires readiness;
- verify readiness value against the readiness enum contract;
- flag readiness that contradicts remaining residual-risk records;
- require readiness source_quote to be non-empty and exact, but do not require the best possible support;
- flag residual-risk details that do not match the required nested risk shape;
- verify residual-risk type against the residual-risk enum contract;
- flag residual risks already answered by feedback;
- flag coverage-only records with empty body or invalid phase-required reason;
- flag packet records that should remain residual risk but were emitted as final requirements;
- do not require suggested-next-workflow output unless the phase contract explicitly requires it;
- do not flag residual risk only because a related question, ambiguity, or missing decision exists elsewhere;
- do not flag source-support quality issues that require redistributing coverage unless the item's own source_quote has no exact support for its detail.

For this flavor, require these inputs when missing:

- packet record enum contract;
- readiness enum contract and shape rules;
- residual-risk enum contract and shape rules;
- feedback section that can resolve risks;
- packet shape invariants, such as exact readiness count.

## Verifier Slice Shape

Draft only this structure:

```text
## Persona Slice: <verify phase job>

### Do

<bounded verifier rules>

### Do Not

<bounded verifier exclusions>
```

## Rules To Enforce

The drafted verifier slice must:

- flag details that do not start with exactly one allowed prefix from the approved enum contract file, followed by `: `;
- flag meaningful record prefixes when the text after the prefix does not satisfy that prefix's phase meaning;
- flag `COVERAGE_ONLY` when the source text states a real record required by the phase;
- flag producer records that combine multiple phase records when the producer contract requires splitting;
- flag missing records only when the source explicitly states the record and no existing valid producer record carries it;
- allow repeated `source_quote` only when repeated records carry distinct valid details;
- state duplicate detection in terms of same needed answer, same constraint, same ambiguity, same decision, or same phase-specific record meaning;
- reject implementation, codebase, file, API, test, or repository output unless the approved phase is code-aware;
- keep every rule tied to verifier findings only.

The drafted verifier slice must not:

- require records from facts outside the provided source;
- infer missing records from what the source does not say;
- flag output only because it could be clearer or better worded;
- flag `COVERAGE_ONLY` only because it is hidden from downstream output;
- independently flag duplicated, overlapping, out-of-order, or uncovered source reconstruction when no `manager-gap-*` record or manager coverage finding exists;
- suggest deleting a `manager-gap-*` record by itself when required coverage would break;
- create producer records;
- create critic patches;
- describe repair implementation beyond the verifier finding's `suggested_change_to`;
- choose or change provider/model;
- use phase-number references unless those exact section labels exist in the verifier input.

## Loop-Safety Check

Before presenting verifier text, compare it against manager behavior and expected critic ownership:

- If the manager owns a mechanical check, verifier may flag the manager finding or final `manager-gap-*`, but must not independently reimplement unstable coverage logic.
- If the critic must repair a finding, `suggested_change_to` must be actionable without asking the critic to infer a new phase rule.
- If a finding would make the critic remove an item that the manager will re-add, revise the verifier text before presenting it.
- If a rule depends on nuanced semantic judgment not required by the phase contract, remove it.

## Approval Gate

When creating or revising persona text, present:

1. existing verifier instructions to remove;
2. exact replacement verifier slice;
3. short alignment check against the producer rules, enum contract, coverage mode, manager checks, and loop-safety risks.

Do not edit the persona until the user approves the exact text.
