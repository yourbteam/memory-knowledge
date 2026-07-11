---
name: critic-foundry
description: Use when creating or revising a workflow phase critic persona. Enforces approval-gated, bounded critic slices from verifier and manager contracts without adding producer, verifier, manager, provider, model, or prompt-specific behavior.
---

# Critic Foundry

Use this skill before creating or revising any phase-specific critic persona.

The skill produces critic slice text only. It does not write producer, verifier, manager, canary, provider, model, or workflow YAML changes.

The skill has two modes:

- create a new critic slice from grounded verifier, producer, and manager contracts;
- audit an existing critic persona and identify whether it contains proven treatment that the foundry contract is missing.

## Baseline From Proven Critics

The common critic baseline is limited to traits that appear across the proven Workflow 2 critic pattern:

- return one strict JSON object with `accepted_findings`, `rejected_findings`, and `producer_patches`;
- accept only verifier findings that identify real phase-contract violations;
- reject findings that depend on implication, inference, absent source text, preference, or cleaner wording;
- emit patches only for accepted verifier findings or explicit patch-repair errors;
- use only supported patch operations: `replace_detail`, `replace_item`, `add_item_after`, `remove_item`;
- include `status: "pending"` and `applied: false` on every new patch;
- preserve required source coverage while patching;
- do not leave `manager-gap-*` records in final producer output;
- do not remove `COVERAGE_ONLY` only because it is hidden from downstream output;
- do not invent producer issues outside verifier findings;
- do not choose or change provider/model.

Do not treat an existing critic persona as correct just because it passes this checklist. The checklist is a floor, not proof of quality.

## Grounding Rule

Ground the slice in current repo files before drafting:

- workflow YAML phase id and output context key;
- critic shared slices already attached to the persona;
- producer enum contract JSON for the phase;
- source coverage mode;
- producer phase-specific rules;
- verifier phase-specific rules;
- manager contract checks and patch applier constraints for the phase.

If any required fact is missing, stop and ask for that fact. Do not invent defaults.

## Existing Critic Audit

When applying this skill to an existing critic persona, do this before recommending changes:

1. List the current phase-specific critic rules.
2. Map each rule to one of:
   - required by verifier rules, producer contract, enum contract, source coverage, manager checks, or patch applier constraints;
   - approved phase-specific behavior;
   - unsupported role leakage or prompt-specific drift.
3. Identify any current rule that handles a real critic problem better than this skill's baseline.
4. Report those as `critic-foundry gaps` before proposing persona edits.

Do not call the skill complete if the existing persona contains useful grounded treatment that the skill would not know to ask about.

Promote an audit-discovered rule into the foundry only when it is a reusable critic-construction rule, not merely wording that makes the audited persona pass. If it is phase-specific, keep it in the proposed critic slice only.

## Required Inputs

Ask only for facts not already grounded in repo files or explicitly approved in the conversation:

- workflow name;
- phase id;
- phase job in one sentence;
- source coverage mode;
- producer record ID prefix;
- enum contract file;
- allowed detail prefixes;
- verifier findings the critic may accept;
- verifier findings the critic must reject;
- valid repair record shape;
- duplicate repair rule;
- manager-gap repair rule;
- coverage-preservation rule;
- patch operation rule.

For multi-record-type phases, also require:

- accepted repair behavior for each meaningful enum value;
- rejected repair behavior for each meaningful enum value;
- incorrect fallback repair rules between enum values;
- source-stated record classes that must not be removed or hidden as `COVERAGE_ONLY`;
- downstream artifact types that must not be created;
- source quote handling when splitting one producer item into multiple records;
- neutral text repair behavior for headings, labels, separators, connector text, transition text, and formatting text.

Do not ask for examples unless the user requests examples.

## Manager Contradiction Gate

Before drafting or auditing critic text, compare it against manager behavior and patch handling.

The critic must not contradict these manager-owned decisions:

- `manager-gap-*` records are temporary coverage repairs and cannot remain in final producer output;
- in `full_universe_coverage`, removing a `manager-gap-*` without preserving its exact source span will make the manager re-add it;
- in `full_reconstruction`, patches must preserve source coverage and reconstruction requirements;
- in `evidence_only`, uncovered source text is allowed and should not be repaired into manager gaps;
- when a neutral manager-gap is repaired by attaching its source_quote to a retained valid item, do not remove the retained item; remove only the manager-gap unless the retained item itself has a separate accepted finding;
- repeated `source_quote` is valid only when retained records have different details;
- same normalized `source_quote` array plus same normalized `detail` is a manager duplicate;
- invalid exact source quotes must be repaired with exact source text, not approximate meaning;
- for repeated neutral source spans such as connector text, punctuation, headings, labels, formatting, or transition text, preserving the same string is not enough. The critic must preserve the same source occurrence the `manager-gap-*` item represents. If the manager-gap `source_quote` is a repeated short span and the repair cannot disambiguate the occurrence through an adjacent exact source span, the critic must not claim the gap is repaired by attaching only that repeated short span to an unrelated retained item;
- `replace_item` must not be used to change `source_quote`;
- when `source_quote` changes, use `add_item_after` for the corrected item and `remove_item` for the invalid item;
- when one patch removes an item, no later patch may reference that removed item;
- every patch must target an existing producer item id and use the payload field required by the patch operation.

If a proposed critic rule can create a patch sequence that the manager cannot apply, or can make the manager re-add the same coverage gap, the rule is invalid.

## Critic Flavors

Select exactly one flavor before drafting or auditing phase-specific text. If the phase does not fit one of these flavors, stop and ask for the intended critic type.

### Phase 1 Atomizer Critic

Use this flavor for the first phase of a workflow when the critic repairs atomized records.

Grounded traits from Workflow 2 Phase 1:

- accept split findings only when the referenced source text explicitly states multiple actionable items for the same actor or role on the same target;
- reject requested splits that depend on implied, inferred, renamed, or absent actions/items;
- reject findings when the explicit items are already represented across separate records;
- repair bundled records by adding one valid single-item record for each explicit item, then removing the bundled record last;
- reuse the original exact `source_quote` when it supports each split item;
- do not remove a bundled record unless added records preserve all explicit items;
- when a manager-gap and a flawed existing item refer to the same underlying item, emit one repair path only;
- do not create duplicate real records with same normalized detail and overlapping source evidence;
- for explicit equivalent labels, remove only duplicate functional records and preserve the equivalence record when source states it.

For this flavor, require these inputs when missing:

- what counts as an atomized item for this workflow;
- producer ID prefix and allowed detail shape;
- equivalence-label rule;
- manager-gap repair rule for atomizer coverage.

### Classification Or Distillation Critic

Use this flavor for phases like Workflow 2 Phases 2, 3, and 4, where the critic repairs one focused finding family.

Grounded traits from Workflow 2 Phases 2-4:

- accept verifier findings only when the referenced source text explicitly satisfies the phase category;
- reject findings that depend on allowed behavior, implication, inference, absent text, or an already represented category finding;
- repair accepted findings by preserving exactly the source-stated category finding and no others;
- repair combined findings by adding one valid single-category record for each explicit category finding, then removing the bundled record last;
- use `add_item_after` for new split records;
- use `remove_item` only after added records preserve every source-stated category finding from the bundled record;
- use the phase enum contract for every repaired detail prefix;
- use `COVERAGE_ONLY` for source coverage records that do not state the phase category;
- accept prefix findings for clear/non-category records and repair them as `COVERAGE_ONLY` when coverage is still needed;
- do not remove `COVERAGE_ONLY` only because it is not emitted downstream.

For this flavor, require these inputs when missing:

- exact phase category;
- enum contract file and allowed prefixes;
- repair rule for each meaningful prefix;
- negative boundary for findings to reject;
- implementation-only repair boundary when relevant;
- duplicate/equivalence repair rule if labels or surfaces can represent the same thing.

### Questions Critic

Use this flavor when the critic repairs question records generated from prior distilled gaps and feedback.

Grounded traits from Workflow 2 Phase 5:

- accept invalid question or coverage findings only when they match the question verifier rules;
- repair accepted findings with valid question records using exact `source_quote`, one allowed detail prefix, and grounded `reason`;
- use the question prefix only for an unresolved upstream gap that needs a missing answer;
- use `COVERAGE_ONLY` when source text must stay covered but does not need a question;
- accept `manager-gap-*` findings when the source text must stay covered but does not need a question;
- repair those manager gaps by replacing or converting them into valid coverage records that preserve the exact manager-gap source_quote;
- remove duplicate question records only when they ask for the same needed answer;
- do not create questions already answered by feedback;
- do not create implementation, codebase, file, API, test, or repository questions unless the phase is explicitly code-aware;
- do not remove a `manager-gap-*` item by itself under `full_universe_coverage`.

For this flavor, require these inputs when missing:

- question enum contract file;
- upstream gap sections that can justify questions;
- feedback section that suppresses questions;
- duplicate-question rule;
- manager-gap-to-coverage repair rule.

### Handoff Packet Distiller Critic

Use this flavor when the critic repairs the final packet for the next workflow.

Grounded traits from Workflow 2 Phase 7:

- when verifier findings are empty, return exactly `{"accepted_findings":[],"rejected_findings":[],"producer_patches":[]}`;
- accept only concrete violations of record prefix, required field, exact source quote, source support, manager-gap, duplicate, packet shape, readiness, residual-risk, or coverage-only rules;
- repair accepted findings using only valid packet record prefixes;
- replace `manager-gap-*` items with valid packet records that preserve the exact manager-gap `source_quote`;
- use `COVERAGE_ONLY` for required source text that does not belong in packet output;
- apply phase-required `COVERAGE_ONLY` reason text when the packet contract requires it;
- remove duplicate items only when the finding identifies a real duplicate by same normalized `source_quote` and `detail`;
- enforce exactly one readiness record when the packet contract requires readiness;
- choose readiness according to residual-risk state and unanswered-question state;
- do not create residual risks already answered by feedback;
- do not repair source reconstruction unless a `manager-gap-*` record or manager coverage finding is present;
- reject findings whose suggested change says no change is needed;
- do not add implementation, codebase, file, API, test, or repository details not present in source.

For this flavor, require these inputs when missing:

- packet record enum contract;
- readiness enum contract and readiness rules;
- residual-risk enum contract and risk rules;
- feedback section that can resolve risks;
- phase-required `COVERAGE_ONLY` reason, if any;
- exact packet shape invariants.

## Critic Slice Shape

Draft only this structure:

```text
## Persona Slice: <repair phase job>

### Do

<bounded critic rules>

### Do Not

<bounded critic exclusions>
```

## Rules To Enforce

The drafted critic slice must:

- state exactly which verifier findings are valid to accept;
- state exactly which verifier findings must be rejected;
- repair accepted findings using only allowed phase record prefixes;
- preserve source-backed meaning when adding, replacing, splitting, or removing records;
- use `add_item_after` for new records, split records, missing source coverage, or corrected items with different `source_quote`;
- use `replace_detail` only when the existing `source_quote` already supports the corrected detail;
- use `replace_item` only when the `source_quote` remains unchanged;
- use `remove_item` only after another retained or added record preserves any required source text and source-stated meaning;
- remove duplicate records only when the verifier finding identifies a real duplicate by the phase-specific duplicate rule;
- repair `manager-gap-*` findings without leaving uncovered source text under `full_universe_coverage` or `full_reconstruction`;
- when repairing a neutral manager-gap by attaching its source_quote to a retained valid item, remove only the manager-gap unless the retained item itself has a separate accepted finding;
- return an empty patch object when verifier findings are empty if the phase has shown a risk of unnecessary critic output.

The drafted critic slice must not:

- accept findings based on facts outside the referenced source text;
- create records not supported by exact source text;
- create implementation, codebase, file, API, test, or repository details unless the approved phase is code-aware;
- remove `COVERAGE_ONLY` only because it is not emitted downstream;
- remove a `manager-gap-*` record by itself when the manager will re-add it;
- reference an item after an earlier patch in the same response removes it;
- use `replace_item` to change `source_quote`;
- change valid patch fields during patch repair unless the manager error identifies that field;
- scan for new producer problems not reported by the verifier;
- choose or change provider/model;
- use phase-number references unless those exact section labels exist in the critic input.

## Patch Safety Check

Before presenting critic text, check it against manager patch handling:

- Every patch operation named in the slice must be supported by the patch applier.
- Every patch must be anchored to an existing producer item id.
- If one patch removes an item, no later patch may reference that removed item.
- If `source_quote` changes, the slice must require `add_item_after` plus `remove_item`, not `replace_item`.
- If a repair removes source text required by coverage, the slice is invalid.
- If a repair can make the manager re-add the same `manager-gap-*`, the slice is invalid.
- For `full_universe_coverage`, a manager-gap repair for repeated neutral text is invalid unless the patched producer source quotes would cover the same source occurrence that produced the manager gap. Reusing the same repeated string elsewhere in the source is not sufficient.
- If the verifier finding is empty, the critic must not invent work.

## Approval Gate

When creating or revising persona text, present:

1. existing critic instructions to remove;
2. exact replacement critic slice;
3. short alignment check against verifier rules, producer rules, enum contract, coverage mode, manager checks, patch operation constraints, and loop-safety risks.

Do not edit the persona until the user approves the exact text.
