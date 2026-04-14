## Scope

Add actor-aware policy and routing behavior based on historical workflow and triage outcomes.

## Planned Work

1. Reuse actor-scoped quality, entropy, convergence, and planning-context summaries as the safe actor-level signals.
2. Add an actor adaptation synthesis layer and read tool.
3. Apply the adaptation summary to advisory triage confidence and clarification posture when an `actor_email` is supplied.
4. Keep sparse-history actors on neutral behavior to avoid overfitting.

## Expected Outcomes

- better defaults for heterogeneous operator and automation sources
- fewer avoidable failures caused by repeated actor-specific input patterns

## Affected Files

- `src/memory_knowledge/admin/actor_adaptation.py`
- `src/memory_knowledge/triage_policy.py`
- `src/memory_knowledge/server.py`
- `tests/test_actor_adaptation.py`
- `tests/test_triage_policy.py`

## Validation

- focused pytest coverage for actor adaptation synthesis
- server wrapper validation for bad input and success payload shape
- triage request assertions for actor-aware confidence and clarification posture
