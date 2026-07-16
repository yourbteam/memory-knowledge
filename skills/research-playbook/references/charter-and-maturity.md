# Charter And Maturity Contract

## Frozen Charter

Create the charter before any research agent starts. It contains:

- stable charter ID and schema version;
- objective and concrete research questions;
- in-scope and excluded surfaces;
- authoritative local and external evidence roots;
- required six-file output package;
- fixed budget and terminal rules;
- requirement records with source, text, maturity, evidence availability, and acceptance intent;
- hash of the canonical charter and requirement set.

Freeze means no field above can change during a run. A requested addition, removal, reinterpretation, or maturity change returns `BLOCKED` with `REQUEST_SCOPE_APPROVAL`; do not mutate the package in place. An approved change starts a new run and new charter hash.

## Requirement Maturity

Assign exactly one maturity to every atomic requirement or claim:

### `CURRENT_RUNTIME`

The requirement asserts how the existing system, stored data, configuration, integration, or deployed behavior works now. Validate it against authoritative current evidence. Missing evidence can block when the claim is required for the handoff.

### `FUTURE_SYSTEM`

The requirement defines behavior that does not exist yet. Validate its source, intent, constraints, compatibility with known boundaries, acceptance criteria, and implementability. Do not demand runtime output, stored values, or deployed behavior from the future system. Record such evidence as `NOT_YET_APPLICABLE`.

### `MIXED`

The source statement combines a present-state premise and a future-state requirement. Split it into linked atomic records before research:

- one `CURRENT_RUNTIME` record for the premise;
- one `FUTURE_SYSTEM` record for the intended change.

`MIXED` is an intake status only. No frozen atomic requirement may remain `MIXED`.

## Evidence Availability

Use exactly:

- `AVAILABLE`: evidence is accessible and indexed;
- `MISSING_REQUIRED`: evidence should exist for a current-runtime claim but is unavailable;
- `NOT_YET_APPLICABLE`: runtime evidence cannot exist for a future-system requirement;
- `EXTERNAL_BLOCKED`: required external evidence exists but cannot currently be accessed.

Never turn `NOT_YET_APPLICABLE` into an invented source or a demand for proof from nonexistent behavior.

## Research Maturity Ceiling

The terminal artifact is ready for an implementation planner, not an implementation plan. Research may establish facts, constraints, requirement intent, alternatives already decided by evidence, acceptance intent, and known limitations. It must hand off, rather than decide:

- exact file-by-file implementation changes;
- code structure choices not fixed by evidence;
- migration sequencing;
- test implementation details;
- deployment or rollout actions.

If research begins choosing those items, classify the finding as planning-stage drift and remove it from the research artifact.
