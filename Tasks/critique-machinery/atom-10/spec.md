# Atom 10 — code-enforced seat input and reply envelopes

Frozen before canonical implementation. The immutable v3 Claude run in `frozen-red/` opened with
the Atom 8 and Atom 9 declaration contracts, launched both seats for all 25 units, and retained 50
raw replies. Forty-seven replies contain one schema-shaped JSON object. Three do not: one is fenced,
one is truncated, and one is prefixed by an operator directive anchor. The first JSON decode error
escaped the seat boundary before any per-cell recording, leaving all 150 applicable cells unjudged.

The approved outcome is one code-owned boundary around each seat call. Code constructs the complete
seat instruction from the immutable unit, lens questions, numbered producer material, and an exact
JSON schema stated in the instruction and supplied to the client. It runs the client from an empty
isolated directory with user/project settings, tools, sessions, commands, and MCP additions disabled
where the installed client exposes those controls. Client behavior that cannot be excluded still
passes through the same deterministic reply intake.

Every attempted seat reply becomes exactly one persisted intake outcome: `valid`, `malformed`,
`empty`, `timeout`, or `nonzero-exit`. A valid outcome contains the schema-checked judgments. Every
other outcome contains the batch, seat, attempt, observed bytes or process result, the exact failure
location when parsing broke, and what would satisfy the contract. Malformed content is never
silently stripped, unwrapped, repaired, or interpreted as semantic judgment.

Initial recording commits one outcome from each seat per cell. A failed seat is visible as
`no-answer`; a valid sibling is retained, every other cell continues, and the operator receives no
run-level exception. `status` accounts for the unique reply outcomes and names retryable failures.
`retry-failed` launches only first-attempt failed batch/seat pairs, writes attempt two beside the
immutable first attempt, and never permits a third attempt. A second failure remains a named
no-answer in the owner queue.

Two independent probes compare materially different approaches on the frozen v3 bytes. The input
probe compares isolated client launch with the current operator-environment launch. The reply probe
compares typed intake plus per-cell recording with wrapper normalization plus whole-batch retry.
The deciding criteria are frozen in `experiment-plan.json`. Promotion requires all 47 valid replies
to record, all three malformed replies to remain visible and unaccepted, all 150 applicable cells
to contain both seat outcomes, zero model calls during replay, and a retry plan containing exactly
the three failed seats.

The v3 source run remains unchanged. Atoms 8 and 9 remain unchanged. Both managed client
projections must be regenerated and installed from the canonical skill after promotion.
