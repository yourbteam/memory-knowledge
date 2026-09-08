# Interview state engine v1

## Entry and authority boundary

`prepare-interview WORK --expected-tip SHA256` derives only the current queue head.
`admit-interview WORK SUBMISSION_JSON --expected-tip SHA256` admits one ordered JSON array
of seat responses. `status`, `advance`, and `verify-replay` independently reconstruct every
interview transition and expose `interview_state`. `response-schema` emits the static contract.

This engine does not launch a model. Envelopes explicitly withhold launch authorization.
Submitted judgments are not proof of process independence, owner permission, or model sharing.
The separately approved launcher atom supplies those operational guarantees. Here, blind seats
mean two separately bound envelopes with identical semantic payloads and no peer response.
Local-only evidence may be prepared locally but must not be transmitted by a launcher.

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
criterion/dependency results, not merely the headline verdict. Different free-text reasons do
not imply disagreement. Dependency discovery prepares the same subject again until `none`,
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
