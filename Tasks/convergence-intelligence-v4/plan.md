## Scope

Add policy and read surfaces that convert loop history into convergence recommendations.

## Planned Work

1. Reuse workflow grade, loop, phase, and validator facts as the canonical convergence signals.
2. Add a synthesis layer that maps repeated failure patterns to intervention recommendations.
3. Expose the result through a dedicated analytics read tool.
4. Include dominant retry phase, dominant failed validator, and grouped recommendation counts.
5. Keep the first version advisory and validate zero-match behavior.

## Expected Outcomes

- lower repeated verifier/fix churn
- faster workflow completion in common failure modes
- better guidance for external orchestrators during retries

## Affected Files

- `src/memory_knowledge/admin/analytics.py`
- `src/memory_knowledge/server.py`
- `tests/test_analytics.py`

## Validation

- focused pytest coverage for convergence recommendation synthesis
- zero-match assertions for empty successful output
- contract checks for dominant phase, dominant validator, and primary recommendation
