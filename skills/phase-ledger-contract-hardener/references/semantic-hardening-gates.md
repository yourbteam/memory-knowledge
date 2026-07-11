# Semantic Hardening Gates

Use these gates after the deterministic attribute audit. They are designed to catch contradictions that mechanical checks miss.

## 1. Responsibility Ownership Gate

For every rule, identify the owner.

- Producer may choose `record_type`, `text`, `source_quote`, and `reason`.
- Producer must not own ids, JSON array shape, coverage gaps, verifier findings, critic patches, or convergence.
- Manager may assign ids, assemble record shape, validate phase-contract fields, account for source coverage, create manager gaps, apply patches, and decide convergence.
- Manager must not semantically reclassify records using `description` or `selection_rules`.
- Verifier may flag violations against source, producer output, manager findings, and the phase contract.
- Verifier must not prescribe patch operations.
- Critic may accept or reject findings and emit supported repairs.
- Critic must not create new findings or remove required coverage without replacement.

Finding trigger: two roles have final authority over the same thing, or no role owns a necessary repair.

## 2. Producer To Manager Handoff Gate

Check whether producer output can always be mechanically accepted or mechanically rejected by the manager.

- The manager must own id assignment when the contract says producer does not.
- The manager must be able to build `detail` from `record_type` and `text`.
- If the producer can emit a value, the manager must know how to validate it from `categories_detail`.
- If the manager can reject a value, verifier/critic must have a repair path.

Finding trigger: the producer is asked to emit structure the manager also claims to own, or the manager can reject something no role can repair.

## 3. Manager Gap Loop Gate

Trace uncovered source text:

1. Manager creates `manager-gap-*`.
2. Verifier flags it.
3. Critic repairs it.
4. Manager validates coverage again.

The loop is unsafe if:

- Critic can remove the gap without preserving required source text.
- Critic is forbidden from creating `COVERAGE_ONLY` when the gap has no category meaning.
- Verifier says delete while manager coverage requires replace/preserve.
- Repair changes `source_quote` using an operation the manager rejects.

Required safe paths:

- Meaningful gap -> category in `categories` with matching `detail_shape`.
- Non-meaningful coverage gap -> `COVERAGE_ONLY` when coverage requires it.
- Evidence-only gap -> remove without replacement.

## 4. Coverage Versus Category Gate

Check whether coverage policy fights category meaning.

- Full reconstruction requires source coverage, not semantic promotion.
- Neutral text must not become a meaningful category unless `categories_detail` says it has meaning.
- `COVERAGE_ONLY` must not satisfy a meaningful category `minimum_count`.
- A meaningful category must not be hidden as `COVERAGE_ONLY`.

Finding trigger: a coverage repair can cause category misuse, or category rules make required coverage impossible.

## 5. Minimum Count Gate

For every category:

- `minimum_count: 0` means no count finding.
- `minimum_count > 0` requires manager/verifier enforcement.
- Critic must be allowed to add a valid source-backed record when missing.
- If source cannot support the missing category, critic must reject rather than invent.

Finding trigger: minimum count requires unsupported content, or critic is required to invent to satisfy it.

## 6. Nested Value Gate

For each `allowed_detail_shape_values` entry:

- It is valid only inside its declaring category.
- Each value has a matching `allowed_detail_shape_value_details[*].value`.
- Producer can choose it using `description` and `selection_rules`.
- Verifier can flag wrong use.
- Critic can repair to another allowed value without changing unsupported source meaning.

Finding trigger: nested values float free from category ownership, or repair would require an unsupported category change.

## 7. Reason Shape Gate

When `reason_shape` is present:

- Producer must use it exactly.
- Manager/verifier enforce it exactly.
- Critic repairs it exactly.
- It must not conflict with the general reason-grounding rule.

Finding trigger: one section requires explanatory reason text while `reason_shape` requires exact boilerplate for the same category.

## 8. Patch Completeness Gate

For each possible verifier finding, confirm at least one supported critic patch can repair it:

- wrong `detail` only -> `replace_detail`;
- same source, wrong shape/reason/category text -> `replace_item`;
- different source quote, split item, missing item, or exact source repair -> `add_item_after` plus `remove_item`;
- unsupported duplicate or invalid item -> `remove_item` only when coverage remains valid.

Finding trigger: verifier can report a real problem that no supported operation can fix.

## 9. Critic Scope Gate

Critic scope is unsafe if it is too broad or too narrow.

- Too broad: critic invents new issues beyond findings.
- Too narrow: critic cannot repair a manager finding or accepted verifier finding.

Finding trigger: critic must look outside findings to converge, or critic is forbidden from repairing something the manager requires.

## 10. All-Actors-Followed-Instructions Gate

For each high-risk path, ask:

> If producer, manager, verifier, and critic all obey this contract exactly, can the loop still fail forever?

If yes, the contract is not ready. Report the specific rule interaction and the smallest contract change needed.
