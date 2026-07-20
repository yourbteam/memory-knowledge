# Plan Package Contract

## Planning inputs

The parent produces one same-revision set:

- `plan.md`: consumer-facing implementation plan.
- `surface-map.json`: exact implementation and verification surfaces.
- `decisions.json`: every material decision locked.
- `verification-ledger.json`: finite obligation inventory and assessment state.

The controller snapshots and hashes the set atomically. Missing, changed, foreign-revision, or unlocked inputs leave state unchanged.

## Required plan content

The plan must provide, in inspectable headings:

1. Goal and terminal outcome.
2. Scope, exclusions, repositories, and allowed paths.
3. Frozen requirement and planner-obligation inventory.
4. Grounded current behavior and evidence anchors.
5. Locked architecture, contracts, and data flow.
6. Ordered implementation steps with file and entry-point anchors.
7. Verification steps with commands and expected observables.
8. Risks, failure handling, rollback or recovery where applicable.
9. Granular implementation approval: exact changes, reason, practical before/after consequence, and estimated implementation/verification cost.
10. Closeout criteria that prove each requirement end to end.

The grounded-current-behavior section includes a preflight table for every claimed file, fixture,
symbol, and verification command. Each row states its frozen source anchor, observed existence or
command authority, and intended `MODIFY|CREATE|DELETE` operation where applicable. The plan may not
say an absent test file or fixture already exists, and may not name an executable without its real
repository invocation. When the repository provides a native full regression-suite command, the
table and verification steps include the focused behavior command followed by the native full-suite
command. An evidence-backed statement that no native full-suite command exists is required when it
is omitted.

For behavior involving parsing, classification, precedence, errors, or state transitions, the
locked contracts include a producer-to-consumer branch matrix. It enumerates each input state,
mixed-state precedence, required semantic validity, downstream rendering/counting/persistence
consumers, expected observable, and verification case. Section presence or schema validity alone
cannot stand in for real data validity. Verification must include malformed inputs, mixed error
states, and the same downstream path used by real consumers whenever those states are in scope.

Reject unresolved alternatives, `either/or`, optional in-scope work, deferred implementation choices, placeholders, and decisions left to the implementer. A decision record has status `LOCKED`, a selected decision, rejected alternatives, requirement IDs, and evidence IDs.

## Surface map

Every in-scope requirement and obligation maps to at least one `PLANNED` surface item containing concrete files, entry points, contracts, implementation steps, verification steps, risk, and evidence. Files remain within frozen repository/path authority. File operations and named anchors must agree with the mandatory pre-draft preflight recorded in `plan.md`. `OUT_OF_SCOPE` requires an approved charter exclusion.

`surface-map.json` contains exactly `schema_version`, `items`, `behavior_matrix`, and `implementation_approval`. Each item contains exactly `id`, `requirement_ids`, `obligation_ids`, `subsystem`, `files`, `entry_points`, `contracts`, `implementation_steps`, `verification_steps`, `risk`, `evidence_ids`, and `status`. Each file contains exactly `repository_key` and repository-relative `path`; `risk` is `high|medium|low`; `status` is `PLANNED|OUT_OF_SCOPE`.

`behavior_matrix` contains exactly `input_states`, `category_exclusions`, `consumers`, and `cases`.
Each input state binds an ID, one of `valid|empty|error|malformed_success|mixed|boundary`, a
description, requirement IDs, obligation IDs, and evidence IDs. Every category is represented by
at least one state or exactly one evidence-backed exclusion, never both. Each consumer binds an ID,
one of `boundary|rendering|aggregate|persistence|external_effect`, a description, and surface-item
IDs; the consumer inventory covers every planned surface. Cases form the exact Cartesian product
of input-state IDs and consumer IDs. Every case binds an ID, expected observable, concrete test
command, and concrete assertion. Missing, duplicate, unknown, or extra pairs fail controller
validation before hardening begins.

`implementation_approval` partitions every PLANNED item into exactly one granular change. Each change states its surfaces, description, reason, repositories, and allowed paths. It also includes exact practical `before` and `after` strings and an estimated cost with implementation effort, verification effort, complexity, and note.

`decisions.json` contains exactly `schema_version` and `decisions`. Each decision contains exactly `id`, `requirement_ids`, `question`, `selected_decision`, `rejected_alternatives`, `evidence_ids`, and `status`. Terminal status is exactly `LOCKED`.

## Profile rules

LIGHT is provisional and remains eligible only for `light` intake, exactly one repository, `change_characteristics=["NONE"]`, exactly one requirement with at most three total obligations, a draft of at most 200 physical lines, and at most 12 deterministic document units. It uses the nine-file package and stores every complete stage report inline in `gate-results.json`.

SUBSTANTIAL applies to `standard|heavy` intake or any LIGHT predicate violation. It uses the twelve-file package and materializes the three owned-lens audit files. Profiles never downgrade; a LIGHT report that cannot fit its complete response artifact escalates once to SUBSTANTIAL and restarts at VERIFY_PLAN on a new round.

## Owned package files

Every package owns exactly these nine files:

```text
plan.md
requirements.json
evidence-index.json
surface-map.json
decisions.json
verification-ledger.json
findings.json
gate-results.json
manifest.json
```

A `SUBSTANTIAL` package additionally owns exactly:

```text
plan.gap-audit.md
plan.coverage-audit.md
plan.satisfaction-audit.md
```

Non-package siblings such as `analysis.md` are allowed. Reserved package filenames not listed in the active profile are rejected.

## Authority and hashes

Root `plan.md` is consumer authority only while controller state is `EMITTED`, no invalidation marker exists, and canonical `validate-package` succeeds. Otherwise the current content-addressed controller snapshot is the sole planning authority. Proposed revisions are scratch; an invalidated emitted package is historical evidence only.

`manifest.json` binds package identity, revision, profile, entry and approval context, charter/requirement/evidence/plan hashes, exact lens contract identity, sorted owned files, ordered stage results, agent lifecycle, budget use, terminal verdict, and emission time. Every consumer must call canonical `validate-package`; it must not parse a relaxed subset.

Its exact top-level fields are `schema_version`, `package_id`, `revision`, `profile`, `entry_mode`, `approval_context`, `approval_authorization`, `charter_sha256`, `requirements_sha256`, `evidence_index_sha256`, `plan_sha256`, `lens_contract_id`, `lens_contract_sha256`, `owned_files`, `stage_results`, `agent_lifecycle`, `budget_use`, `terminal_verdict`, and `emitted_at_utc`. `owned_files` is the sorted exact `{path,sha256}` set excluding the manifest itself.

`gate-results.json` records all four stages on the same plan hash. LIGHT embeds complete response-sized artifacts. SUBSTANTIAL binds the three exact audit files. The three owned-lens stages all use `PLAN_PLAYBOOK_V2_HARDENING_LENSES_V1` and one raw-byte contract hash.

Its exact top-level fields are `schema_version`, `plan_sha256`, `lens_contract_id`, `lens_contract_sha256`, `profile`, `stages`, and `terminal_verdict`. Every stage contains exactly `round`, `stage`, `lens_contract_id`, `lens_contract_sha256`, `terminal_verdict`, `role_results`, `terminal_envelope_sha256`, and `artifact`. Every artifact contains exactly `form`, `path`, `content_markdown`, and `sha256`; INLINE requires null path and complete Markdown, while FILE requires its exact package-relative path and null inline content.

## Emission and invalidation

Emission is a manifest-last, journaled transaction in the frozen task root. It validates staged bytes before replacing owned files, backs up the prior owned set, publishes `manifest.json` as the commit point, revalidates, and recovers or rolls back deterministically after interruption.

A material post-emission plan change uses `prepare-revision` and `record-revision`, never a direct root edit. The controller durably publishes `.plan-package-invalidated.json` before state leaves `EMITTED`. All consumers remain blocked until the successor passes all four stages, is emitted and validated, and the matching marker is removed.
