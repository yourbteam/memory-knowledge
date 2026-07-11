---
name: phase-categorization-foundry
description: This skill should be used when creating or auditing a non-mechanical workflow phase categorization enum contract and its integration into personas, prompt injection, manager validation, composers, and tests. It grounds categories in the phase purpose, upstream inputs, downstream consumers, and the proven Workflow 2 plus Workflow 3 Phase 1 patterns.
---

# Phase Categorization Foundry

Use this skill before creating or revising any non-mechanical workflow phase that emits phase-ledger producer records.

The goal is not to make a broad taxonomy. The goal is to create the smallest useful categorization contract that lets the phase do its job, lets subscribers consume the output, and lets the manager mechanically validate record prefixes without hardcoded enum drift.

## Required Inputs

Before proposing categories, inspect the repo for:

- The software constitution section for the workflow and phase. Use it to determine the phase purpose, boundary, consumes, produces, and rules.
- The executable workflow YAML phase id, name, description, input source, dependencies, subscriptions, source coverage mode, and output context key.
- The workflow catalog text for display names and catalog descriptions.
- The phase's direct upstream inputs and direct downstream subscribers.
- Existing enum contracts in `src/workflow_orch/contracts/enums/` and `software company workflows/enums/`.
- Existing persona text for producer, verifier, and critic.
- Existing manager/parser/composer/prompt-injection code for the phase output context key.

Purpose rule:

- Determine phase purpose from `software company workflows/Software Delivery Workflow Constitution.md`.
- Use YAML as source of truth for executable wiring: phase id, dependencies, subscriptions, input source, coverage mode, output context key, provider/model, and role agents.
- If constitution purpose and YAML wiring disagree, do not silently merge them. Report the mismatch and ground categories in the constitution purpose only after the executable mismatch is acknowledged or resolved.

If any required phase purpose, upstream source, or downstream consumer is missing from repo truth, ask for that missing decision before drafting the contract.

## Contract Design Rules

- Use a JSON enum contract file for every non-mechanical phase's top-level record categories.
- Keep categories phase-owned. Do not reuse another phase's enum file unless the phase is explicitly the same contract surface.
- Keep values few, mutually exclusive, and actionably named.
- Include `COVERAGE_ONLY` for phases using source universe or reconstruction coverage when some source text must be retained but should not emit downstream substance.
- Add nested enum contracts only when a top-level category needs bounded subtypes, such as `READINESS` or `RESIDUAL_RISK`.
- Do not use examples, implementation mechanisms, or prompt-specific nouns as enum values.
- Do not encode final prose output labels as categories unless subscribers need that distinction.
- Do not hardcode category values only in personas or manager branches. The contract JSON must be the source; manager constants may use `load_enum_contract`, `load_json_contract`, and `require_contract_value` to fail fast when the JSON changes.

## Creation Workflow

1. Identify the phase purpose from the software constitution, then verify the executable YAML wiring that will carry that purpose.
2. Identify the phase kind:
   - Atomizer: splits an upstream packet/source into primitive records.
   - Classification/distillation: extracts one purpose-specific kind of fact from upstream records.
   - Question foundry: emits bounded operator questions or coverage records.
   - Handoff/packet distiller: emits final packet records plus readiness/residual-risk categories when needed.
3. Draft the smallest enum values that cover the constitution-grounded phase responsibility.
4. Check each value against upstream and downstream:
   - The producer can choose it from source text.
   - The verifier can flag misuse without semantic overreach.
   - The critic can repair accepted findings without inventing new phase behavior.
   - The manager can validate prefix shape mechanically.
   - A subscriber can understand why the record matters.
5. Create mirrored contract files:
   - `src/workflow_orch/contracts/enums/<phase-owned-name>.json`
   - `software company workflows/enums/<phase-owned-name>.json`
6. Wire manager integration:
   - Load ordered values from the JSON contract.
   - Require mandatory values with `require_contract_value` when code branches need named values.
   - Parse detail by iterating ordered contract values and requiring `"<VALUE>: <text>"`.
   - Add duplicate/detail/shape reports as needed for the phase.
   - Route manager findings and composer output by the phase's output context key.
7. Wire prompt injection:
   - Inject the contract by phase id plus output context key when ids are reused across workflows.
   - Include the filename and JSON payload in the prompt.
   - State the mechanical prefix rule once: every non-manager producer item detail starts with one allowed prefix followed by `: `.
8. Wire personas only with approved text:
   - Producer: use the injected contract as the only category source.
   - Verifier: flag invalid prefix and category/source mismatches.
   - Critic: repair accepted findings using only allowed categories.
   - Do not add phase-specific persona wording without exact approval.
9. Add tests for mirror files, prompt injection, manager detail parsing, composer routing, persona references, and no stale enum references.

## Audit Workflow

For an existing phase, report:

- Contract file: present or missing in both mirrors, byte-aligned or not.
- Purpose source: constitution phase purpose found or missing, and whether YAML/catalog agree with it.
- Contract fit: each value maps to phase purpose and output consumers, with no broad catchall except `COVERAGE_ONLY`.
- Prompt injection: phase prompt includes the correct filename and JSON values.
- Persona integration: producer/verifier/critic reference the injected contract and do not use stale enum filenames from another phase.
- Manager integration: parser and detail report load from the contract values, not a private list.
- Composer integration: output labels and suppression rules match the contract.
- Test integration: tests prove prompt injection, manager validation, composer behavior, and stale-reference absence.
- Risk: identify any category that is too broad, overlapping, ungrounded, or only useful to the current prompt rather than the phase contract.

## Grounding References

Read [workflow2-and-workflow3-categorization-patterns.md](references/workflow2-and-workflow3-categorization-patterns.md) when creating or auditing a phase in this repo. It records the concrete Workflow 2 and Workflow 3 Phase 1 category contracts, manager wiring, prompt injection, and persona integration patterns.

## Output Format

For creation:

```text
Contract proposal:
- filename:
- values:
- nested contracts:
- why each value exists:
- values rejected:
- integration files to update:
- tests to add:
```

For audit:

```text
Status:
- aligned:
- gaps:
- hardcoded enum risks:
- stale references:
- recommended fixes:
```

Keep recommendations grounded, bounded, and tight. Do not invent persona instructions or category values beyond the phase purpose and consumer need.
