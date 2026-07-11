---
name: phase-ledger-contract-hardener
description: This skill should be used when semantically auditing or hardening phase-ledger universal orchestration contracts, injectable contracts, role prompt assembly contracts, or phase-specific category contracts. It checks full phase-contract attribute usage, role responsibility boundaries, contradictions between producer/manager/verifier/critic behavior, and unrecoverable loop risks before hollow-persona migration or universal contract changes.
---

# Phase Ledger Contract Hardener

Use this skill before changing or approving phase-ledger universal contracts, hollow persona prompt assembly, or phase-specific category contracts.

The goal is not to prove that files parse. The goal is to prove that the phase loop can converge when producer, manager, verifier, and critic each follow their instructions.

## Required Inputs

Ground these from repo files before asking the user:

- Injectable universal contract document.
- Phase-specific category contract document for the target phase.
- Optional shared-slice migration audit when validating migration completeness.
- Any manager behavior document or code path referenced by the contract.
- Any current phase persona text only when checking whether the new contract preserves existing proven behavior.

Ask only when the target phase, contract path, or intended mode is not discoverable.

## Workflow

1. Read the injectable universal contract and phase-specific category contract.
2. Run the deterministic audit script:

```bash
python3 /Users/kamenkamenov/.codex/skills/phase-ledger-contract-hardener/scripts/contract_attribute_audit.py \
  --universal <universal-contract.md> \
  --phase <phase-contract.md>
```

3. If migration completeness is part of the task, compare the shared-slice migration audit against the current shared-slice inventory.
4. Read `references/semantic-hardening-gates.md` and perform the semantic pass manually.
5. Report findings first. Do not edit contracts unless the user explicitly approves implementation.

## Required Analysis

### Attribute Coverage

Every phase contract attribute must be used explicitly by the universal contract:

- `contract_key`
- `id_prefix`
- `categories`
- `categories_detail`
- `category`
- `description`
- `selection_rules`
- `detail_shape`
- `minimum_count`
- `allowed_detail_shape_values`
- `allowed_detail_shape_value_details`
- `value`
- `reason_shape`

For each category, verify:

- `category` appears in `categories`.
- `minimum_count: 0` means no minimum enforcement.
- `allowed_detail_shape_values` is scoped only to the category that declares it.
- `allowed_detail_shape_value_details[*].value` matches `allowed_detail_shape_values`.
- `reason_shape` is enforced only when present.

### Responsibility Boundaries

Check that the contract assigns one owner for each responsibility:

- Producer identifies source-backed records and chooses categories.
- Manager owns IDs, structure, mechanical validation, coverage accounting, and convergence.
- Verifier flags violations and final-state requirements.
- Critic repairs accepted verifier/manager findings with supported patches.

Flag any rule that gives two roles final authority over the same decision.

### Loop Safety

A contract is unsafe when every actor can follow instructions and the loop still cannot converge.

Check at minimum:

- Verifier requires a final state critic cannot patch.
- Critic may remove coverage that manager will re-add as `manager-gap-*`.
- Manager creates gaps the verifier/critic are forbidden to repair.
- `COVERAGE_ONLY` can fight category `minimum_count`.
- Exact-source quote repairs cannot be expressed by allowed patch operations.
- Nested enum errors cannot be repaired without inventing unsupported category meaning.

## Output Format

Use this shape:

```text
Status:
- deterministic audit:
- semantic audit:

Findings:
- [severity] [owner boundary / contradiction / loop risk / attribute coverage] ...

No-change confirmations:
- ...

Recommended surgical changes:
- ...

Do not change without approval:
- ...
```

Keep findings grounded in exact contract attributes and role interactions. Do not add broad advice, examples, or phase-specific behavior unless it is present in the phase contract.
