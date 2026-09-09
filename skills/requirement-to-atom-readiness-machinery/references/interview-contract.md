# Interview state engine v1

## Entry and authority boundary

`prepare-interview WORK --expected-tip SHA256` derives only the current queue head.
`admit-interview WORK SUBMISSION_JSON --expected-tip SHA256` admits one ordered JSON array
of seat responses. `status`, `advance`, and `verify-replay` independently reconstruct every
interview transition and expose `interview_state`. `response-schema` emits the static contract.

Preparation and admission do not launch a model. Envelopes explicitly withhold launch authorization.
Submitted judgments are not proof of process independence, owner permission, or model sharing.
The opt-in launcher below supplies the transport and permission boundary. Here, blind seats
mean two separately bound envelopes with identical semantic payloads and no peer response.
Local-only evidence may be prepared locally but must not be transmitted by a launcher.

## Opt-in Codex launcher

`prepare-launch WORK LAUNCH_DIRECTORY --expected-tip SHA256` freezes the current prepared
interview as `plan.json`, plus readable per-seat prompts and schemas. This does not call a model
or change the readiness ledger. Use a separate new launch directory outside the readiness work
directory and outside repository/instruction ancestry. The plan binds prompt and schema bytes,
seat identities, the pending interview, ledger tip, launcher identity, explicit provider/model/
effort, timeout, isolation settings and exact call count.

The plan retains both the canonical response schema and its provider projection. The latter
replaces unsupported `uniqueItems` keywords with explicit uniqueness guidance at every nested
array. Returned data must still pass the unchanged canonical local validator, including
uniqueness, before admission. The authorized schema hash binds the actual provider bytes.
The CLI's startup unstable-feature notice is suppressed through its documented setting;
provider errors and tool events remain failures, not ignored warning aliases.

`launch-interview WORK LAUNCH_DIRECTORY AUTHORIZATION_JSON --expected-tip SHA256` requires a
trusted owner authorization with exactly `schema_version: 1`,
`decision: "authorize-exact-payload"`, nonempty `owner`, exact `plan_sha256`, `provider`, `model`,
`reasoning_effort`, `max_calls` equal to twice the complete seat count, and future UTC `expires_at_utc`.
The hash-bound plan declares `timeout_retries_per_seat: 1`: the budget includes one initial
process and at most one conditional timeout retry for each seat (four processes for two seats).
This receipt is supplied through the trusted operator channel; the launcher validates its scope,
not human presence or a cryptographic owner signature. Interview response text cannot authorize
a launch. Never manufacture this receipt from a model response or infer it from build approval.

Evidence fitness establishes eligibility for local preparation, not model transmission. Both
local-only and model-authorized labels may pass local fitness; denied or secret evidence may not.
The launcher requires every selected evidence item to carry model-authorized classification AND
the separate exact-payload owner receipt. A label, receipt reference, or public sensitivity alone
never permits a call. The owner must inspect all prompt content, including subjects and criteria,
not just evidence labels. No unlisted source is fetched to fill missing context.

Before any transmission, one hash-bound reservation is appended to the readiness ledger for that
prepared attempt. Copying the launch directory, creating another plan, or repeating after a crash
cannot reserve the same pending interview again. Every seat runs as a fresh `codex exec` process
in an empty directory, with user configuration/rules ignored, project instruction bytes disabled,
tool/context-discovery features disabled, explicit OpenAI model/effort, read-only sandbox and no
resume, fallback provider, or unbounded transport retry. Only a small inherited environment
allowlist is passed; existing Codex authentication is used without copying or printing credentials.

Preparation inventories local user, admin and bundled skill paths and freezes explicit
`skills.config` disables in the authorized plan. It reads paths, not skill contents. The inventory
is bounded, follows links with cycle detection, and is rechecked before each reader process;
new or removed skill paths require a fresh plan. Historical replay validates the frozen list
without requiring today's skill installation to remain identical. No installed skill, account
configuration, HOME or CODEX_HOME value is changed. CLI permission/environment instructions
remain; "isolated" does not mean that the provider's base instructions disappear.

There is one initial reader process per seat. Only the launcher's typed deadline expiry permits
one automatic retry for that same seat, with byte-identical prompt/schema and a fresh empty
process directory. Authority expiry, runtime identity and isolation checks run before the retry.
Completed seats are not called again. Provider errors, invalid output, missing completion,
disagreement, and authority failures never trigger this recovery. Both attempts and the selected
final result are retained and validated on replay; a second timeout stops the launch without a
semantic fact. This bounded recovery policy was owner-approved on 2026-09-09.

The built-in
OpenAI provider retains its bounded network retry behavior within each process's five-minute
deadline; the seat count is not a count of HTTP requests. Built-in provider retry fields must not
be overridden through `model_providers.openai`: the supported CLI rejects those overrides before
launch. Those provider-internal bounds are unchanged from 2026-09-08.
Exhausted recovery or a non-timeout failure consumes the prepared attempt and retains an
engine rejection. A second preparation is allowed only within the original declared engine
attempt budget and requires a fresh exact-payload approval. Interrupted reservations are not
automatically retried; their state remains visible for explicit recovery. Success of transport
does not imply semantic agreement: admission still applies the existing paired-response rules.

The launcher fixes `RUST_LOG=warn` rather than inheriting debug/trace, retains warnings privately,
and emits byte-count/elapsed-time progress every fifteen seconds. Timeout telemetry records
cause as unconfirmed; bounded recovery does not claim to diagnose or prevent provider stalls.

The launcher retains command, authorized prompt/schema, provider stdout/stderr and response bytes
inside immutable interview transactions before admitting responses. Local structured telemetry
records reservation, seat start/completion, failure and terminal outcome. Prompt/schema and each
retained output member are bounded to 128 KiB. Oversized failure output retains its bounded prefix
and full hash/size; it cannot become success. The process group is terminated on timeout and any
remaining descendants are terminated when the leader exits. Provider failure, invalid schema,
missing completion telemetry or observed tool use cannot fall back or produce an admitted fact.
Preflight refusals are recorded in local launch telemetry and do not reserve or transmit anything.

## Explicit semantic obligation (approved prerequisite)

An evidence condition may carry `interview`. Old conditions remain readable but cannot be
interviewed without the explicit descriptor. The descriptor lists its family, subject IDs,
evidence references and exact quotes, source-bound criteria, explicit maturity for sufficiency, candidate dependencies, complete
owner choices and answer type, and an atom candidate only for cohesion. No source text or
condition name is used to guess the family. Foreign/duplicate IDs, absent quotes, irrelevant
field families, missing criteria, unregistered dependencies and invented authority are refused.
Every criterion source must also have selected evidence metadata, including sensitivity and
sharing restrictions. The graph preserves the validated descriptor without granting any fact.

## Family contracts

| Family | Verdicts | Additional constrained response | Proposed fact only |
| --- | --- | --- | --- |
| Evidence bearing | supports, refutes, irrelevant, cannot_assess | One subject and evidence item, exact source quote | Bearing judgment; no support edge is created |
| Evidence sufficiency | satisfied, insufficient, contradictory, cannot_assess | Every declared criterion, its evidence IDs and result | Sufficiency judgment; no readiness certification |
| Dependency discovery | dependency, none, cannot_assess | One remaining listed ID plus requires, or null plus none | Proposed requires fact; rejects self/foreign/repeated/cyclic edges |
| Contradiction assessment | compatible, conflict, cannot_assess | Two registered claims with both evidence anchors | Compatibility judgment; a conflict is not resolved by a model |
| Verification adequacy | adequate, inadequate, cannot_assess | Every listed criterion with evidence and outcome | Adequacy judgment; failed mechanical evidence cannot be overridden |
| Atom cohesion | cohesive, must_split, cannot_assess | Exact complete candidate requirement set | Cohesion judgment; no new requirement, path or approval |
| Owner-question formulation | formulated | One question, exact answer type and complete choices | Proposed wording only; never an owner answer |

`cannot_assess` never maps to a fact. Positive sufficiency/adequacy requires every criterion
satisfied; negative overall results cannot contradict an all-satisfied criterion set. Free-text
reasons are audit-only. Owner wording is bounded to one line and question; its semantic quality
is not certified by punctuation checks and it cannot execute instructions or grant authority.

All families require two matching blind seats except owner-question formulation, which uses one.
Code validates exact seat/run/node/attempt/envelope identities, closed schemas, the complete
evidence-ID set, exact source quotes and family-specific coverage. Agreement includes structured
criterion identities and outcomes/dependency results, not merely the headline verdict.
Different valid criterion citation selections or ordering do not imply disagreement.
Each seat must still cite nonempty registered evidence for every criterion, cover the
complete presented evidence set overall, and supply the exact source quotes. Accepted
criterion conclusions carry separate `criterion_evidence_by_seat` attribution; no union
or first-reader citation list is presented as jointly agreed support. Exact original
responses remain in the submission record. Different free-text reasons do not imply
disagreement. This applies equally to sufficiency and verification adequacy. Existing
runs retain their source-bound runtime and are not reinterpreted by this correction.
Dependency discovery prepares the same subject again until `none`,
removing proposed IDs; each question has the declared bounded retry budget. Other shared nodes
produce one fact exactly once, even when linked to several requirements.

## Durability, refusals and limits

The immutable start ledger remains unchanged. Each interview transition extends its hash chain
in a separately published numbered transaction directory. Preparation stores both envelopes and
their response schemas. Admission stores the exact bounded response bytes in base64, their hash,
and the independently derived acceptance or rejection. Replay rebuilds the outcome from bytes.
An atomically replaced head receipt detects missing tail transactions. The head is a local
integrity receipt, not an external signature against coordinated rewriting of all run files.

Exclusive locking and expected-tip checks prevent cooperating writers from double admission.
Rejected submissions are retained, including malformed or unsolicited duplicates, but never add
a fact. Stale commands and inaccessible, linked or oversized submission files are refused before
capture. Responses are limited to 1 MiB; transaction events to 4 MiB; transitions to 1024; response arrays to 256 items.
Interrupted publication, changed members, unexpected files, gaps and head mismatch fail closed;
this atom does not automatically repair or discard incomplete transactions.

Facts stay in `interview_state.proposals` with `authority: proposed-only`. The original graph,
queue, requirement dispositions and readiness remain unchanged. The later phase-routing atom
consumes proposals and routes negative findings or owner questions; this atom cannot silently
skip unresolved conditions to reach a model call.

## Captured-case proof boundary

The verification case uses retained independent research responses about evaluator self-trust.
The test driver preserves their bytes and source hashes, then explicitly adapts transport IDs
and `self-trust-confirmed` to the approved `inadequate` enum for that same question. These are
test-only replay judgments, not historical production responses and not fresh live model calls.
The semantic subcase is extracted explicitly; the full returning-discount queue is separately
checked to remain blocked at its earlier MySQL condition. Rejection cases are mutations of those
captured judgments. No product system, provider or consent flow is exercised or changed here.
