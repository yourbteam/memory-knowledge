## Scope

Design and implement outcome-aware routing adjustments for triage decisions.

## Planned Work

1. Reuse the existing triage outcome and lifecycle fields as the canonical routing outcome inputs.
2. Add an explicit outcome-weighted route summary in the triage policy layer grouped by request kind, workflow, and run action.
3. Add a dedicated MCP read tool that returns the adaptive routing summary for operators and integrator LLMs.
4. Add an explicit route-failure penalty to triage search ranking so historically costly routes are directly penalized.
5. Expose top outcome-weighted routes in `triage_request_with_memory`.
6. Validate sparse-history and zero-match behavior through focused tests.

## Expected Outcomes

- more conservative routing in historically costly request classes
- stronger reuse of successful routing patterns
- less manual interpretation of routing analytics

## Affected Files

- `src/memory_knowledge/triage_policy.py`
- `src/memory_knowledge/triage_memory.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_policy.py`

## Validation

- focused pytest coverage for the new route-summary tool
- ranking feature assertion for explicit route-failure penalty
- confirmation that `triage_request_with_memory` exposes outcome-weighted route context
