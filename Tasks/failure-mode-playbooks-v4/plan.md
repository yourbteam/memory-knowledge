## Scope

Create reusable playbooks for recurring workflow and triage failure signatures.

## Planned Work

1. Reuse findings, convergence, and triage confusion summaries as the canonical failure signatures.
2. Define normalized playbook codes and action recommendations.
3. Expose the mapping through a dedicated read tool.
4. Keep the first version advisory and repository-aware.
5. Validate successful empty output and input validation behavior.

## Expected Outcomes

- less repeated manual interpretation of known failures
- stronger operator and orchestrator guidance
- better consistency in how similar failures are handled

## Affected Files

- `src/memory_knowledge/admin/playbooks.py`
- `src/memory_knowledge/server.py`
- `tests/test_playbooks.py`

## Validation

- focused pytest coverage for playbook synthesis
- contract checks for confidence, suggested actions, and source counts
- server wrapper validation for bad input and success payload shape
