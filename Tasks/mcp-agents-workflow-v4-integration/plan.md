## Scope

Create a repo-tracked integration package that tells `mcp-agents-workflow` exactly how to adopt the deployed V4 `memory-knowledge` upgrade surface.

This task covers:

- a task artifact trail under `Tasks/mcp-agents-workflow-v4-integration/`
- a dedicated `mcp-agents-workflow` integration guide in `docs/`
- explicit call-site guidance for the new V4 MCP tools
- validation and rollout guidance for the external integrator

This task does not cover:

- modifying `mcp-agents-workflow` directly in this repo
- changing the already-deployed `memory-knowledge` server implementation

## Implementation Steps

1. Write `analysis.md` for the task with grounded current-state facts and integration constraints.
2. Write a focused integration guide for `mcp-agents-workflow` covering:
   - the purpose of the V4 upgrade
   - the exact new tool surfaces
   - the orchestrator decision points where each tool should be called
   - the required request inputs, especially `actor_email`
   - expected output usage patterns
   - rollout order
   - smoke validation steps
   - failure and fallback behavior
3. Write `plan.md` documenting scope, artifacts, validation, and closeout.
4. Manually harden the guide content against the existing server contracts already documented in:
   - `docs/LLM_INTEGRATION_GUIDE.md`
   - `docs/AGENT_INTEGRATION_SPEC.md`
5. Close out with a concise summary of what another LLM should do next in `mcp-agents-workflow`.

## Affected Artifacts

- `Tasks/mcp-agents-workflow-v4-integration/analysis.md`
- `Tasks/mcp-agents-workflow-v4-integration/plan.md`
- `docs/MCP_AGENTS_WORKFLOW_V4_INTEGRATION.md`

## Validation

- Ensure every referenced V4 tool exists in the current documented server surface.
- Ensure the guide distinguishes:
  - server-owned behavior
  - orchestrator-owned behavior
- Ensure the guide states what happens if the external system does nothing:
  - compatibility remains
  - adaptive behavior is not activated
- Ensure the guide includes a concrete adoption sequence rather than only prose descriptions.

## Dependencies And Sequencing Notes

- This guide depends on the already-completed V4 server deployment.
- The external `mcp-agents-workflow` repo should consume this guide after updating to the current live server contract.

## Closeout Checklist

- [x] Task folder created
- [x] Analysis written
- [x] Plan written
- [x] Dedicated integration guide written
- [x] Guide aligned to documented V4 tool contracts
