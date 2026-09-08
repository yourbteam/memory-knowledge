# Readiness request contract

Atom 4 provides only schema, start, status and verify-replay. All other commands below describe later atoms and are unavailable.
`python3 scripts/readiness_controller.py schema` prints the contract without reading input.

## Runtime root and write boundary

Every command requires an explicit absolute `--work` path. The controller rejects a work path that is:

- equal to, below, or above any declared target repository;
- equal to or below any declared product edit boundary;
- a symbolic link or contains a symbolic-link ancestor below the first existing parent;
- non-empty at `start`; or
- outside the owner-authorized runtime root recorded in the request.

All machinery writes remain below `--work`. The machinery never writes into a target repository,
`Tasks/`, a source evidence directory, or a temporary location not owned by the run. Final reports and
handoff files are part of the run and therefore durable. Copying them into a repository is a separate
owner-authorized action, not controller behavior.

Inputs are copied exactly once into a content-addressed run store. The controller does not recursively
copy a repository. Directories are inadmissible as evidence unless supplied as a deterministic manifest
whose members, sizes, and hashes are explicit. This prevents both product-surface contamination and
per-case bundle amplification seen in the retained Dropbox telemetry.

## Runtime and serialization contract

Version 1 is Python 3 standard-library code only. It adds no package-manager or runtime dependency.
JSON Schema files document every external contract, while the controller itself enforces exact keys,
types, enums, cardinalities, numeric bounds, and cross-record identities with code-owned validators.
The implementation must not depend on `jsonschema`; the retained missing-runtime failure proves that an
undeclared validator dependency would make the operator path non-replayable.

All state-bearing JSON is UTF-8 encoded, has no byte-order mark, and ends with one line feed. Canonical
JSON used for identity and hashing is serialized with sorted object keys and separators `(',', ':')`,
with no insignificant whitespace, before SHA-256. JSONL events use one independently canonical JSON
object plus one line feed per event. Human-readable projections may be indented, but their hashes cover
their actual bytes. IDs derived from content always name both the schema version and canonical input
fields in their contract so a later version cannot silently collide.

The running controller records `sys.executable`, its resolved regular-file identity, Python version, and
file hash at `start`; every subprocess uses that same interpreter. A resume under different interpreter
identity is refused rather than silently changing serialization or validation behavior.

The only v1 semantic provider is the installed OpenAI Codex CLI. At `start`, the controller resolves the
`codex` launcher from `PATH`, records the discovered launcher path and link target, requires the resolved
target to be a regular file, and records its real path, version output, and file hash. The request selects
an explicit model identifier and reasoning effort;
the launcher passes them to `codex exec` together with `--ignore-user-config`, `--ignore-rules`,
`--ephemeral`, `--skip-git-repo-check`, `--sandbox read-only`, `--output-schema`, and
`--output-last-message`; it supplies the model with `--model` and the effort with the strict configuration
override `-c model_reasoning_effort=<value>`. Provider abstraction, a second provider, or an implicit
host-default model is a versioned extension, not an implementer option.

Each seat receives a newly created empty `WORK/model/<interview-id>/<seat>/cwd` and the launcher refuses
that directory if any repository or instruction-file ancestry is detected. Readiness-affecting semantic
families use exactly two blind seats. Owner-question wording uses exactly one seat. No other seat count is
valid in v1.

## Public operator interface

The controller exposes these commands and no implicit mutation path:

```text
readiness_controller.py start REQUEST_JSON WORK
readiness_controller.py status WORK
readiness_controller.py advance WORK
readiness_controller.py admit-evidence WORK REQUEST_ID EVIDENCE_MANIFEST
readiness_controller.py prepare-interview WORK
model_interview.py run WORK INTERVIEW_ID
readiness_controller.py admit-interview WORK INTERVIEW_ID RESPONSE_JSON
readiness_controller.py answer-owner WORK DECISION_ID ANSWER_JSON
readiness_controller.py correct-owner WORK DECISION_ID PRIOR_EVENT_ID ANSWER_JSON
readiness_controller.py admit-atom-candidates WORK CANDIDATES_JSON
readiness_controller.py compile-package WORK
readiness_controller.py approve-atoms WORK APPROVAL_JSON
readiness_controller.py export-next-atom WORK
readiness_controller.py admit-atom-completion WORK ATOMIC_STEP_ID ATOM_RUN
readiness_controller.py verify-replay WORK
```

Exit codes are stable:

| Code | Meaning |
| ---: | --- |
| 0 | Command completed and state is valid; inspect the returned status |
| 2 | Request or answer refused before mutation |
| 3 | Replayed state is `blocked` |
| 4 | Replayed state is `needs_owner` |
| 5 | A prepared model interview is the single next action |
| 6 | State is `ready` but atom approval is absent or rejected |
| 7 | The exact next approved atom handoff is available |

Every mutating command takes an expected ledger-tip hash. A stale caller is refused without writing.
`status` and `verify-replay` are read-only.

## Start request

`readiness-request.json` contains exactly:

```json
{
  "schema_version": 1,
  "feature_id": "stable-owner-supplied-id",
  "runtime_boundary": {
    "authorized_root": "/absolute/durable/run-root",
    "target_repositories": ["/absolute/repository"],
    "product_edit_boundaries": ["/absolute/repository/path"]
  },
  "model_runtime": {
    "provider": "openai-codex-cli",
    "model": "explicit-model-id",
    "reasoning_effort": "explicit-supported-effort"
  },
  "execution_limits": {
    "max_input_files": 1000,
    "max_single_file_bytes": 104857600,
    "max_total_input_bytes": 1073741824,
    "model_timeout_ms": 300000,
    "max_model_attempts_per_seat": 2
  },
  "description_handoff": {"path": "/absolute/description-handoff.json", "sha256": "..."},
  "requirements_handoff": {"path": "/absolute/requirements-handoff.json", "sha256": "..."},
  "boundaries": {"path": "/absolute/task-boundaries.json", "sha256": "..."},
  "evidence_manifests": [{"path": "/absolute/evidence.json", "sha256": "..."}],
  "machinery_contracts": [{"role": "stable-contract-role", "path": "/absolute/file", "sha256": "..."}],
  "telemetry_manifests": [{"path": "/absolute/telemetry.json", "sha256": "..."}],
  "blocker_ledgers": [{"path": "/absolute/events.jsonl", "sha256": "..."}],
  "owner_records": [{"path": "/absolute/owner-answer.json", "sha256": "..."}]
}
```

Every execution limit is mandatory; there are no hidden defaults. The controller accepts only positive
integers and applies these hard v1 ceilings: 10,000 files, 1 GiB per file, 10 GiB total, 600,000 ms per
model attempt, and two attempts per seat. A request may choose lower values. Exceeding either the
request value or hard ceiling is a deterministic refusal, never a retry or model decision. The explicit
model and effort are frozen at `start`; a provider rejection is retained as that seat attempt's exact
failure rather than silently falling back to another model or effort.

Machinery-contract roles are unique. Version 1 requires
`working-agreement`, `description-skill`, `description-exporter-source`, `requirements-skill`,
`requirements-controller-source`, `info-intake-skill`, `sequence-runner-skill`,
`experiment-machinery-skill`, `prototype-driven-implementation-skill`, `atom-building-skill`,
`atom-controller-source`, and `blocker-catalog-source`. Missing or duplicate roles block `start`.

Every path is only an import location. `start` verifies the supplied hash, rejects links and unsupported
file types, copies the bytes below `WORK/inputs/objects/<sha256>`, rehashes the copy, and records origin,
role, logical identity, byte size, import time, and object path. After admission, no controller decision
reads the origin path.

Changing any listed byte, boundary, requirement set, authority record, freshness rule, or controller
schema requires a new run. Resume never silently reimports drifted input.


## Atom 4 operator contract

Create an empty external work directory yourself. Run `readiness_controller.py start REQUEST WORK --expected-tip 0000000000000000000000000000000000000000000000000000000000000000`. Read-only `status WORK` and `verify-replay WORK` reconstruct the initialized state. They do not assess readiness. The schema command remains read-only.

Start imports only explicitly named descriptor files, not handoff members or directory contents; semantic trust belongs to the next adapter atom. Files and the request are frozen beneath `WORK/run/`, with content-addressed inputs, canonical ledger and state projection. Publication renames one completed staging directory within WORK. Exclusive directory locking serializes starts; every expected-tip mismatch refuses before writes. Replay works in memory, compares stored projection bytes, checks object membership and runtime identities, and never rereads source origins. No model invocation occurs: only local `codex --version` identification.
