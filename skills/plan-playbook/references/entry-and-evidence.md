# Entry and Evidence Contract

## Frozen charter

Planning begins from one immutable charter with exactly:

- `schema_version=1`
- non-empty `objective`
- `allowed_repositories`, keyed by stable repository key and canonical absolute root
- repository-relative `allowed_paths`
- nullable `supplied_input_root`
- `exclusions`, `deliverables`, and `approval_boundaries`
- sorted, duplicate-free `change_characteristics`

`change_characteristics` is either `["NONE"]` or a non-empty subset of `MIGRATION`, `ROLLOUT`, `MULTI_REPOSITORY`, and `EXTERNAL_STATE`. It contains `MULTI_REPOSITORY` exactly when more than one repository is allowed. Scope expansion or a charter mismatch returns `BLOCKED/SCOPE_CHANGED`; it is not repaired by silently widening the plan.

## Entry modes

Choose exactly one mode.

### DIRECT

The parent supplies requirements and evidence in the research package's canonical requirement/obligation shape. Every obligation is already `READY` and has non-empty implementation anchors, verification anchors, required inputs, ownership, closure condition, and evidence IDs.

Each evidence record has exactly `id`, `requirement_ids`, `facets`, `source`, `supported_claim`, and `limitations`. `source.kind` is:

- `LOCAL_FILE`: names a frozen repository key and repository-relative regular file.
- `SUPPLIED_INPUT`: has null repository key and resolves beneath the charter-bound immutable supplied-input root.

The controller reads the bytes, rejects symlinks and root escape, and verifies the asserted SHA-256. For each requirement, the union of evidence facets contains `CURRENT_BEHAVIOR`, `IMPLEMENTATION_OWNERSHIP`, and `ACCEPTANCE_OBSERVABLE`. `CURRENT_BEHAVIOR` includes at least one controller-read `LOCAL_FILE`; supplied claims alone cannot establish it.

DIRECT does not accept dynamic command, query, runtime, or live-data output. Such evidence returns `BLOCKED/RESEARCH_REQUIRED` so the research package can capture provenance.

## Mandatory pre-draft repository preflight

After evidence binding and before drafting, the parent verifies every concrete claim the plan will
hand to an implementer against the controller-owned source snapshots:

- Every existing file and fixture is present at the stated repository-relative path. A new file is
  explicitly labelled `CREATE`; it is never described as existing or as containing fixtures.
- Every named symbol, entry point, parser rule, producer, and consumer is located in frozen source.
- Every verification command is derived from checked-in project configuration, a repository-owned
  launcher, or captured tool help. The plan uses the exact executable path and working directory.
- When checked-in project configuration or a repository-owned launcher exposes a native full
  regression-suite command, verification includes both the narrowest focused command for the
  changed behavior and that native full-suite command, in that order. If no native full-suite
  command exists, the preflight records that evidence-backed absence instead of inventing one.
- Every allowed implementation path is classified as `MODIFY`, `CREATE`, or `DELETE`, and that
  operation agrees with snapshot existence.

Record these facts in the plan's grounded-current-behavior section and surface map anchors. A
missing or contradictory preflight fact returns `BLOCKED/RESEARCH_REQUIRED`; the parent does not
draft around it or leave rediscovery to the implementer.

When behavior depends on classification, parsing, precedence, errors, or state transitions, the
parent also inventories the complete boundary before drafting: upstream producer, input-state
partitions, precedence rules, downstream consumers and aggregates, user-visible observables, and
one verification case for every materially distinct branch. Mixed states such as error plus
partial output are explicit rows, not assumed to follow the happy path.

The parent records that inventory in the controller-validated `behavior_matrix` in
`surface-map.json`. It must disposition `valid`, `empty`, `error`, `malformed_success`, `mixed`,
and `boundary` input categories with either grounded states or evidence-backed exclusions, declare
every affected boundary, renderer, aggregate, persistence sink, and external effect, and provide
one exact command and assertion for every declared state-by-consumer pair. The draft is invalid
when any pair is absent, duplicated, or unbound.

### RESEARCH_PACKAGE

With no package, initialize only the frozen charter and return `BLOCKED/RESEARCH_REQUIRED`; requirements and evidence remain unbound. Resume only from the deterministic controller-prepared bundle and a package that passes the research owner's canonical read-only `validate-package` boundary.

A valid research package has exactly its six owned files, terminal `PASS`, intact manifest and artifact hashes, and one `READY` planner record per obligation. Planning consumes its normalized `requirements` and `evidence_index` without field conversion or schema invention.

## Direct task-root selection

For an explicit direct invocation:

1. Canonicalize the charter and compute `charter_sha256`.
2. Strict-resolve the current working directory and allowed repository roots.
3. Select the unique deepest allowed repository containing the working directory. No match or an equal-depth tie returns `BLOCKED/TASK_ROOT_UNRESOLVED` and creates nothing.
4. Build `base` from the first six maximal ASCII alphanumeric runs in the lowercased objective, joined with `-`, truncated to 48 ASCII characters with a trailing `-` removed; use `plan` when empty.
5. Use exactly `<repository>/Tasks/<base>-<charter_sha256[:12]>`.

Create only absent `Tasks/` and task-root directories after checking all existing path components without following symlinks. Reuse an existing root only when its controller state binds the same root and charter hash. Otherwise return `BLOCKED/TASK_ROOT_COLLISION`. Never add a numeric suffix, timestamp, or alternate repository.

Task-workflow owns and supplies its existing `Tasks/<slug>/` root; it does not use direct root derivation.

## Evidence change and resume

Before a draft, `resume` is the only evidence-binding path. After a draft, evidence changes use the mode-correct `prepare-revision` input and a controller-validated `record-revision`; the wrong mode argument fails closed. A valid revision preserves history, consumes no invented evidence, and invalidates every old stage result.
