# Convergence Stage Result Contract

When a stage is delegated by `playbook-convergence-loop`, run in assessment-only mode: inspect and report, but do not edit, commit, or mutate task state. The parent orchestrator is the only fixer and state writer.

End with one fenced `stage-result` JSON object:

```json
{
  "stage": "research-coverage",
  "iteration": 1,
  "attempt": 1,
  "assigned_requirement_ids": ["R1"],
  "assigned_gap_ids": [],
  "owned_blocker_ids": [],
  "verdict": "PASS",
  "open_gap_ids": [],
  "closed_gap_ids": [],
  "new_gaps": [],
  "new_blockers": [],
  "record_transitions": [{"kind": "gap", "id": "G1", "from_status": "open", "to_status": "closed", "evidence": "exact closure evidence"}],
  "evidence": ["path:line or command result"],
  "artifact_paths": []
}
```

Verdicts are exactly `PASS`, `GAPS`, `BLOCKED`, or `CAP_REACHED`.

- `PASS`: the complete assigned surface was checked and no owned blocker gap remains.
- `GAPS`: actionable gaps exist; include complete records in `new_gaps` or existing IDs in `open_gap_ids`.
- `BLOCKED`: required evidence or tooling is unavailable to the parent runtime; include a complete blocker record. A delegated agent lacking child-spawn tools is not a blocker when the parent can manage agents.
- `CAP_REACHED`: the stage cap was reached with unresolved gaps.

Every existing open gap listed in `closed_gap_ids` requires exactly one matching `record_transitions` entry with non-empty closure evidence. Previously terminal gaps need no repeated transition.

Execution blockers progress one evidence-bearing transition per stage attempt: `open -> fixed-awaiting-verification -> verified -> closed`. `PASS` requires every owned blocker terminal; `BLOCKED` persists the task as blocked while any owned blocker is non-terminal.

Fresh reasoning context excludes producer rationale, hidden expected answers, prior conversational reasoning, and producer explanations. It includes the objective, requirement IDs/text, target artifact, authoritative source roots, exact commands, raw findings, and raw closure evidence required to verify the stage.
