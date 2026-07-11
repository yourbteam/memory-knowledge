---
name: phase-ledger-category-contract-foundry
description: This skill should be used when creating or auditing a phase-specific category contract for the phase-ledger hollow-persona/general-manager flow. It grounds the contract in the target workflow phase purpose, executable YAML, legacy enum/persona/manager behavior, upstream inputs, downstream consumers, and an optional reference contract such as Workflow 3 Phase 6.
---

# Phase Ledger Category Contract Foundry

Use this skill to create or audit phase-specific category contract files for contract-backed phase-ledger phases.

The skill's job is not to make nice documentation. Its job is to produce the smallest mechanically usable phase contract that lets the universal orchestration contract, general hollow personas, and general contract manager run the phase without phase-specific persona instructions.

## Modes

- `create`: create a new contract for a target workflow phase. A reference contract may be provided for structure only.
- `audit`: check an existing contract against repo truth and the universal orchestration contract.

Do not edit files by default. Report grounded findings and a proposed contract/change list first. Contract creation or edits require explicit user approval.

## Required Inputs

Ground these from repo files before drafting or auditing:

- Target workflow name and phase id/name.
- Optional reference contract path, used only for shape and field naming.
- Optional existing target contract path for audit.
- Universal orchestration contract path when checking compatibility.
- Whether the phase uses a prepared code project checkout as evidence.

If the target workflow or phase cannot be resolved from repo files, ask for that missing identifier before drafting.

## Required Grounding Pass

Run the helper script first. It requires PyYAML, so invoke it with `uv run
python` from the repo root (the working directory `uv` resolves the project/venv
from); running it as bare `python3` or from another directory will abort with
`PyYAML is required to inspect workflow YAML`:

```bash
uv run python /Users/kamenkamenov/.codex/skills/phase-ledger-category-contract-foundry/scripts/phase_contract_inventory.py \
  --repo-root <repo-root> \
  --workflow <workflow-name> \
  --phase <phase-id-or-name> \
  --reference-contract <optional-reference-contract.md> \
  --target-contract <optional-existing-contract.md>
```

Then inspect the files the script reports. At minimum, read:

- Software Delivery Workflow Constitution phase section.
- Executable workflow YAML phase config.
- Workflow catalog phase entry.
- Legacy enum contract files and mirrors.
- Legacy producer, verifier, and critic personas for the phase.
- Manager/parser/composer code and relevant tests reported by the script.
- Universal orchestration contract, especially `phase_contract_attribute_usage`, `code_project_checkout_usage`, `detail_entry_optional_fields`, and source-universe evidence-boundary rules.
- Recent canary fixtures/results when they exist and are relevant to proven behavior.

Do not treat the reference contract as semantic truth for the target phase. It is a structural example only.

## Contract Creation Rules

Create contracts with this structure:

- `contract_key`: stable phase-owned key.
- `id_prefix`: manager-owned record id prefix.
- `phase_purpose`: one practical sentence describing the phase job.
- `input_context`: one practical sentence describing the source text and, for code-grounded phases, the prepared code checkout evidence.
- `categories`: strict list of allowed source-backed producer categories.
- `source_structure`: optional mechanical hints for source labels/headings.
- `categories_detail`: one entry per category with `category`, `description`, `selection_rules`, `detail_shape`, and `minimum_count`.
- `detail_literal_evidence_source`: optional category-level field. Allowed values are `source_quote` and `code_project_checkout`; absent means `source_quote`.
- `allowed_detail_shape_values`: only inside the category that needs bounded nested values.
- `allowed_detail_shape_value_details`: explanations for each nested value, scoped to the declaring category.
- `reason_shape`: only when a category has an exact mechanical reason requirement.
- `derived_outputs`: only for manager-owned outputs that are computed after source-backed records validate.
- `output_composition`: phase-owned final text sections, skip categories, section order, and dedupe rule.
- `input_contract_preconditions`: only terminal validity rules that cannot be repaired by inventing records.

Keep category descriptions and selection rules grounded in the phase purpose, upstream input shape, downstream consumer need, and legacy proven behavior. Keep them short enough to be injected into a prompt without becoming noise.

For code-grounded phases that use a prepared code project checkout as evidence, `input_context` must say the phase uses that checkout. Any category whose `detail` may legitimately contain code symbols, paths, routes, functions, classes, or other checkout-backed literals that are not present in `SOURCE REQUEST` should declare `detail_literal_evidence_source: "code_project_checkout"`. Categories that remain source-text-only should omit the field or use `source_quote`.

## Universal vs Phase-Specific Boundary

Keep universal behavior out of phase contracts:

- exact source quote mechanics;
- full-universe/full-reconstruction coverage policy;
- manager ownership of IDs and JSON structure;
- producer/verifier/critic role responsibilities;
- patch operations and convergence behavior;
- no invention/no semantic overreach rules.

Put phase-specific behavior into the phase contract:

- allowed categories and nested values;
- what each category means for this phase;
- how to choose between categories;
- phase-specific required minimum counts;
- manager-derived outputs for this phase;
- final output composition sections for this phase;
- source labels/headings the prompt renderer may mechanically surface;
- `phase_purpose` and `input_context` text for hollow persona context;
- category-level detail literal evidence source when code-checkout evidence is allowed.

If a discovered legacy rule looks universal, report it under `universal_contract_candidate` instead of copying it into the phase contract.

## Create Workflow

1. Resolve target phase from workflow YAML and catalog.
2. State the phase job in one sentence from the constitution, not from vibes; this becomes `phase_purpose`.
3. List direct upstream inputs, downstream consumers, and source text shape; this becomes `input_context`.
4. Determine whether the phase uses a prepared code project checkout and whether any categories need checkout-backed detail literals.
5. List legacy categories, nested enums, output sections, and manager/composer rules.
6. Decide the minimum source-backed category set.
7. Decide whether any output should be manager-derived rather than producer-emitted.
8. Draft the contract JSON.
9. Check the draft for internal consistency with the helper script.
10. Run the phase-ledger contract hardener deterministic audit when a universal contract is available.
11. Report findings and the proposed contract; do not write it unless approved.

## Audit Workflow

For an existing contract, report:

- whether the JSON parses and uses the required structure;
- whether top-level `phase_purpose` and `input_context` exist and are practical, phase-specific sentences;
- whether every `categories_detail[*].category` appears in `categories`;
- whether nested value details match nested values;
- whether `minimum_count` rules are grounded and non-inventive;
- whether derived outputs are truly manager-computable;
- whether output composition matches legacy composer/downstream expectations;
- whether `detail_literal_evidence_source` values are valid, absent only when source-quote evidence is enough, and present as `code_project_checkout` for code-symbol/path-bearing categories in code-grounded phases;
- whether code-grounded phases mention the prepared checkout in `input_context` and align with `code_project_checkout_usage` from the universal contract;
- whether any Phase 6 semantics were copied without target-phase need;
- whether any phase-specific behavior is missing from the contract.

## Output Format

For create:

```text
Grounded findings:
- phase job:
- phase purpose field:
- input context field:
- upstream inputs:
- downstream consumers:
- legacy categories:
- legacy output/composer behavior:
- universal-contract candidates:
- code-checkout/detail-literal evidence decisions:

Proposed contract:
```json
...
```

Open risks:
- ...
```

For audit:

```text
Status:
- parse:
- grounding:
- contract fit:
- manager compatibility:
- output compatibility:

Findings:
- ...

Recommended changes:
- ...
```

Keep recommendations tight and grounded. Do not add examples or phase-specific wording unless the target phase evidence requires it.
