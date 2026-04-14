## Scope

Add policy-driven clarification behavior derived from prior triage ambiguity patterns.

## Planned Work

1. Expand the existing clarification policy payload with freshness, mode, and inferred missing-field guidance.
2. Reuse historical clarification questions as the base evidence for suggested prompts and required fields.
3. Add a dedicated read tool that returns the strongest matching clarification policy for a route.
4. Expose the required clarification contract in `triage_request_with_memory`.
5. Validate that low-history cases remain advisory and zero-match cases return a clean empty contract.

## Expected Outcomes

- fewer premature workflow selections
- lower ambiguity-driven failure rates
- more consistent clarification prompts across similar request classes

## Affected Files

- `src/memory_knowledge/triage_policy.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_policy.py`

## Validation

- focused pytest coverage for the new required-clarification tool
- contract checks for enriched clarification policy fields
- triage response assertions for surfaced clarification requirements
