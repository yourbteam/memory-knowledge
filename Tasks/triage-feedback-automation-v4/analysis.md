## Objective

Define the next major product-facing upgrade after triage V3: a V4 feedback automation layer that turns workflow and triage history into active routing, clarification, and convergence behavior instead of passive reporting only.

## Task Type And Size

- Type: roadmap/program planning
- Size: standard

## Current-State Facts

- The repository already supports:
  - workflow telemetry persistence
  - workflow findings persistence
  - workflow analytics summaries
  - triage memory persistence and search
  - triage policy synthesis
  - adaptive ranking improvements
- The current future roadmap item is still broad:
  - "Deeper Workflow/Triage Feedback Automation"
- Practical upgrade value comes from moving from reporting to policy adaptation.

## Recommended Program Shape

Break V4 into six slices:

1. outcome-weighted routing
2. clarification policy learning
3. convergence intelligence
4. failure-mode playbooks
5. actor/team adaptation
6. policy governance and rollout controls

## Why This Structure

- It keeps early slices user-visible and product-relevant.
- It separates policy generation from governance.
- It allows staged delivery without losing the end-state architecture.
- It creates executable task artifacts that can be run independently.
