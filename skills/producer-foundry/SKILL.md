---
name: producer-foundry
description: Use when creating or revising a workflow phase producer persona. Enforces approval-gated, bounded producer slices from the phase contract without adding verifier, critic, manager, provider, model, or prompt-specific behavior.
---

# Producer Foundry

Use this skill before creating or revising any phase-specific producer persona.

The skill produces a producer slice only. It does not write verifier, critic, manager, canary, provider, model, or workflow YAML changes.

The skill has two modes:

- create a new producer slice from a grounded phase contract;
- audit an existing producer persona and identify whether the persona contains proven treatment that the foundry contract is missing.

## Baseline From Proven Producers

The common producer baseline is limited to traits that appear across the proven Workflow 2 producer pattern:

- strict JSON-array output through shared producer slices;
- exactly `id`, `source_quote`, `detail`, and `reason`;
- approved ID prefix;
- exact source quotes from the provided input;
- no facts outside the provided input;
- enum-contract-backed detail prefixes;
- one meaningful record per emitted detail;
- `COVERAGE_ONLY` for source coverage that does not satisfy the phase job;
- same `source_quote` reuse only when the same span supports distinct details;
- no manager, verifier, critic, provider, or model behavior in producer text.

Do not treat an existing persona as correct just because it passes this checklist. The checklist is a floor, not proof of quality.

## Grounding Rule

Ground the slice in current repo files before drafting:

- workflow YAML phase id and output context key;
- producer shared slices already attached to the persona;
- enum contract JSON for the phase;
- source coverage mode;
- manager contract checks for the phase when they exist.

If any required fact is missing, stop and ask for that fact. Do not invent defaults.

## Existing Producer Audit

When applying this skill to an existing producer persona, do this before recommending changes:

1. List the current phase-specific producer rules.
2. Map each rule to one of:
   - required by workflow YAML, enum contract, source coverage, or manager checks;
   - approved phase-specific behavior;
   - unsupported role leakage or prompt-specific drift.
3. Identify any current rule that handles a real producer problem better than this skill's baseline.
4. Report those as `producer-foundry gaps` before proposing persona edits.

Do not call the skill complete if the existing persona contains useful grounded treatment that the skill would not know to ask about.

Promote an audit-discovered rule into the foundry only when it is a reusable producer-construction rule, not merely wording that makes the audited persona pass. If it is phase-specific, keep it in the proposed persona slice only.

## Required Inputs

Ask only for facts not already grounded in repo files or explicitly approved in the conversation:

- workflow name;
- phase id;
- phase job in one sentence;
- input source shape;
- source coverage mode;
- record ID prefix;
- enum contract file;
- allowed detail prefixes;
- what counts as a real record;
- what must be `COVERAGE_ONLY`;
- what must not be emitted;
- source reuse rule.

For multi-record-type phases, also require:

- the decision rule for each meaningful enum value;
- the rule that prevents one enum value from becoming a fallback for another;
- source-stated record classes that must not be dropped or collapsed into `COVERAGE_ONLY`;
- downstream artifact types the producer must not create even when the phase domain is related to them;
- the source quote granularity rule when one source span can contain multiple recordable items;
- the neutral text coverage rule for headings, labels, separators, connector text, transition text, and formatting text.

Do not ask for examples unless the user requests examples.

## Manager Universe Coverage Gate Awareness

Before drafting or auditing a producer for `full_universe_coverage`, account for the manager's mechanical gate:

- every `source_quote` string must appear exactly in `## SOURCE REQUEST`;
- the producer source_quote arrays must cover every non-separator part of `## SOURCE REQUEST` at least once;
- whitespace-only and separator-only gaps are ignored by the manager;
- numbered-list separators such as list numbering are ignored when they are only separators;
- meaningful text after a separator is not ignored and will become a `manager-gap-*` if uncovered;
- repeated `source_quote` use is allowed only when each record has a different detail;
- records with the same normalized `source_quote` array and same normalized `detail` are duplicates;
- uncovered source text is appended by the manager as `manager-gap-*` records with empty `detail`;
- `manager-gap-*` records must be resolved before convergence;
- multi-entry `source_quote` arrays can cover non-contiguous source spans, including spans that appear out of source order, as long as each string is exact source text;
- repeated connector spans can be covered by pairing the connector with adjacent unique source text in the same record's `source_quote`.

For `full_universe_coverage`, the producer slice must give the persona a practical coverage strategy:

- cover meaningful source text with a phase record when it satisfies the phase job;
- cover meaningful source text with `COVERAGE_ONLY` when it does not satisfy the phase job;
- attach connector, heading, label, separator, transition, formatting, or neutral text to a nearby valid record when that is safer than creating standalone coverage records;
- create standalone `COVERAGE_ONLY` only when the phase contract allows it and no nearby valid record can safely carry that exact source span;
- do not create `manager-gap-*` records; the manager owns them.

Before drafting or auditing a producer for `full_reconstruction`, account for the manager's mechanical gate:

- producer source_quote arrays must collectively reconstruct the full `## SOURCE REQUEST` text in source order;
- uncovered source text may be converted into `manager-gap-*` records;
- final output cannot converge while `manager-gap-*` remains.

Before drafting or auditing a producer for `evidence_only`, account for the manager's mechanical gate:

- every emitted `source_quote` string must appear exactly in `## SOURCE REQUEST`;
- uncovered source text is allowed;
- producer text should not ask for full coverage or manager-gap repair.

## Producer Flavors

Select exactly one flavor before drafting or auditing phase-specific text. If the phase does not fit one of these flavors, stop and ask for the intended producer type.

### Phase 1 Atomizer

Use this flavor for the first phase of a workflow when the producer turns an input packet or prompt into primitive source-backed records for later phases.

Grounded traits from Workflow 2 Phase 1:

- split only explicit actionable requirements, permissions, prohibitions, scope rules, or preservation rules;
- when one source span states multiple explicit actions for the same actor or role on the same target, emit one record per action;
- allow the same exact `source_quote` only when one source span supports each split record;
- do not split background, rationale, or business-context text only because it has commas, `and`, `or`, or multiple clauses;
- do not invent actions that are not explicitly present;
- if equivalent labels are explicitly stated and affect duplicate functional records, preserve the equivalence and avoid duplicate functional records.

For this flavor, require these inputs when missing:

- what counts as an actionable primitive in this workflow;
- whether equivalence labels are in scope;
- whether source_quote granularity should be full source sentence/span or narrower clause boundaries.

### Classification Or Distillation Producer

Use this flavor for phases like Workflow 2 Phases 2, 3, and 4, where the producer classifies primitive records into one focused finding family.

Grounded traits from Workflow 2 Phases 2-4:

- emit a meaningful record only when the source explicitly satisfies the phase category;
- emit one category finding per `detail`;
- use the enum contract to choose the prefix;
- use `COVERAGE_ONLY` when source text must remain covered but does not satisfy the phase category;
- do not infer from what the source does not say;
- do not treat every requirement condition as the phase category;
- do not combine multiple category findings in one `detail`;
- allow repeated `source_quote` only when one primitive source contains multiple distinct category findings;
- write one sentence after the prefix.

For this flavor, require these inputs when missing:

- the exact phase category;
- the meaningful enum values and their decision rules;
- the negative boundary: what looks related but must not be emitted;
- whether implementation mechanics are excluded;
- duplicate/equivalence handling if labels or surfaces can represent the same thing.

### Questions Producer

Use this flavor when the producer converts prior distilled gaps plus feedback into operator-answerable questions.

Grounded traits from Workflow 2 Phase 5:

- read composed phase outputs as the source, not as free-form raw requirements;
- apply feedback first and do not ask questions already answered by feedback;
- emit a question only for an unresolved upstream gap that must be answered before the packet can be completed;
- ask for the missing answer needed to close the gap, not whether the gap exists;
- question details must be one concrete operator-answerable question ending with `?`;
- do not ask implementation, codebase, file, API, test, or repository questions unless the phase is explicitly code-aware;
- do not ask broad questions such as `What should be done?`;
- do not emit multiple questions for the same needed answer;
- cover composed section headings as source text, but do not turn headings into questions.

For this flavor, require these inputs when missing:

- which upstream gap sections can generate questions;
- which feedback section answers or suppresses questions;
- what question prefix is allowed by the enum contract;
- whether composed section headings are present and must be covered.

### Handoff Packet Distiller Producer

Use this flavor when the producer composes the final packet for the next workflow from completed source sections and feedback.

Grounded traits from Workflow 2 Phase 7:

- emit final packet records only from provided input sections;
- emit one final requirement record for each downstream-ready requirement sentence;
- emit exactly one readiness record when the packet contract requires readiness;
- use readiness and residual-risk enum contracts, not free text categories;
- emit residual risk only for unresolved upstream ambiguity, decision, or unanswered-question records after feedback is applied;
- do not create residual risks for questions already answered by feedback;
- use `COVERAGE_ONLY` for source text that must remain covered but does not emit packet output;
- do not invent implementation, codebase, file, API, test, or repository details;
- do not drop required source sections; represent them as packet output or cover them.

For this flavor, require these inputs when missing:

- final packet record enum contract;
- readiness enum contract, if readiness is required;
- residual-risk enum contract, if residual risks are allowed;
- source sections that can emit final requirements;
- source sections that can emit residual risks;
- feedback section that resolves questions or risks;
- exact readiness rules.

## Producer Slice Shape

Draft only this structure:

```text
## Persona Slice: <phase job>

### Do

<bounded producer rules>

### Do Not

<bounded producer exclusions>
```

## Rules To Enforce

The drafted producer slice must:

- use the approved ID prefix exactly;
- require `detail` to start with exactly one allowed prefix from the approved enum contract file, followed by `: `;
- use the approved enum contract values and descriptions as the only classification contract;
- state when to emit each meaningful record type;
- state when not to use each meaningful record type;
- state which source-stated record classes must not be dropped or hidden as `COVERAGE_ONLY`;
- state when to emit `COVERAGE_ONLY`;
- state the exact source reuse rule;
- state how to quote source when one source span contains multiple recordable items;
- define source quote granularity in concrete text-boundary terms when granularity is narrower than a full sentence;
- state how neutral text is covered under `full_universe_coverage`;
- keep every rule tied to producer output only.

The drafted producer slice must not:

- add fields outside `id`, `source_quote`, `detail`, and `reason`;
- create `manager-gap-*` records;
- create verifier findings;
- create critic patches;
- describe repair behavior;
- choose or change provider/model;
- inspect repo/code/API/test details unless the approved phase is code-aware;
- create downstream artifacts that belong to later phases, even when the source domain is related;
- use phase-number references unless those exact section labels exist in the producer input.

## Approval Gate

When creating or revising persona text, present:

1. existing producer instructions to remove;
2. exact replacement producer slice;
3. short alignment check against the enum contract, coverage mode, source quote granularity, neutral text coverage, and manager checks.

Do not edit the persona until the user approves the exact text.
