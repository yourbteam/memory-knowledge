## Objective

Produce a concrete integration handoff for `mcp-agents-workflow` so the external orchestrator can actively use the deployed V4 adaptive triage and workflow-guidance upgrades exposed by the live `memory-knowledge` MCP server.

## Task Classification

- Type: integration documentation and handoff planning
- Size: standard

## Current-State Facts

- The `memory-knowledge` server now exposes additional V4 tool surfaces for adaptive routing, clarification, convergence, failure-mode handling, actor adaptation, and governance rollout.
- The server-side implementation is already live and deployed.
- The existing integration documents in this repo describe the server contracts, but they do not yet provide a focused, stepwise upgrade guide specifically for `mcp-agents-workflow`.
- `mcp-agents-workflow` already owns the orchestration behavior, phase sequencing, and tool-calling policy; it does not automatically benefit from new server tools unless its prompts and runtime decision points are updated.

## Source Artifacts Inspected

- `docs/LLM_INTEGRATION_GUIDE.md`
- `docs/AGENT_INTEGRATION_SPEC.md`
- Recent V4 implementation context already grounded in:
  - `src/memory_knowledge/server.py`
  - `src/memory_knowledge/triage_policy.py`
  - `src/memory_knowledge/triage_memory.py`
  - `src/memory_knowledge/admin/analytics.py`
  - `src/memory_knowledge/admin/playbooks.py`
  - `src/memory_knowledge/admin/actor_adaptation.py`

## Constraints

- Do not re-specify server behavior that is not actually implemented.
- Do not invent `mcp-agents-workflow` internals that are not grounded by the known integration boundary.
- The handoff must be useful to another LLM, which means it must state:
  - what changed
  - when to call each new tool
  - what parameters matter
  - how to order the calls
  - what behavior must change in the external orchestrator
- The handoff should preserve backward compatibility expectations:
  - existing flows can continue without the new tools
  - the upgrade is needed to activate the new adaptive behavior

## Risks

- Overstating the server contract would cause the external integrator to rely on fields or policies that do not exist.
- Under-specifying tool usage points would leave the external LLM with a descriptive document but no executable integration path.
- Mixing server ownership with orchestrator ownership would create bad architecture drift.

## Recommended Approach

- Create a dedicated integration guide aimed specifically at `mcp-agents-workflow`.
- Make the guide operational rather than descriptive:
  - map each new tool to an orchestration decision point
  - define minimum required behavior changes
  - define an implementation order
  - define smoke checks and success criteria
- Record the work in a repo task folder so the handoff is traceable under the standard task workflow.
