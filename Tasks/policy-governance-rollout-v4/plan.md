## Scope

Add governance and rollout controls for V4 adaptive policies.

## Planned Work

1. Reuse the existing artifact governance fields as the rollout-control baseline.
2. Add a consolidated rollout summary read tool.
3. Compute promotion candidates, suppression pressure, and drift review signals from current artifacts.
4. Keep the first version read-only and advisory.

## Expected Outcomes

- safer rollout of adaptive behavior
- better operator trust in routing and convergence policy changes
- clearer auditability of policy evolution

## Affected Files

- `src/memory_knowledge/triage_policy.py`
- `src/memory_knowledge/server.py`
- `tests/test_triage_policy.py`

## Validation

- focused pytest coverage for governance summary output
- server wrapper validation for required input
- confirmation that rollout recommendations derive from existing artifact metadata
