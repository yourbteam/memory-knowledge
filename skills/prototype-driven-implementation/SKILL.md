---
name: prototype-driven-implementation
description: Central controller for every code implementation, from routine mechanical changes to uncertain features and root fixes. Drive the work through a bounded, adaptive sequence of runnable prototypes grounded in real code paths and captured real cases, pulling PDI-owned bounded planning, coding, blocking-evidence, and retained-surface support only when observed gaps require them. Do not use for standalone research, document-only planning, or review with no implementation.
---

# Prototype-Driven Implementation

Own the complete implementation lifecycle. Reach the approved user-visible goal through the fewest
evidence-producing prototypes, and let each observed outcome select the next unresolved gap. Do
not invent a complete implementation roadmap upfront.

## Freeze the autonomy envelope

Before editing, state one compact envelope containing:

- the concrete user-visible outcome and stopping condition;
- allowed repositories and paths;
- the real captured success and failure cases available for proof;
- the maximum elapsed time or prototype attempts;
- excluded actions such as commits, deployments, destructive changes, credentials, and external
  messages.

Obtain explicit approval for that envelope before edits. The approval covers autonomous prototype
progress only when the governing working agreement recognizes this skill as an authorization
mechanism; otherwise retain its existing change-by-change approval gates.

## Run the adaptive loop

Start with **Prototype 0**. Exercise the real production path to reproduce, characterize, or
directly prove the current behavior before broad implementation research or planning. If the
change is routine and mechanical, Prototype 0 may establish the exact delta and become the only
prototype after direct verification.

For each prototype:

1. Observe the current production path and identify the earliest unresolved behavior that prevents
   the approved outcome.
2. State one testable hypothesis, the smallest product-code delta needed to test it, and the exact
   proof that will decide the outcome.
3. Exercise the real code path with captured real inputs. Include both a real success case and a
   real failure case when the behavior has a rejection boundary. Never substitute invented data
   when captured evidence exists.
4. Monitor actual runtime evidence while the prototype runs. Record the earliest deviation and
   trace producer, persisted or runtime state, and consumer before changing the diagnosis.
5. Give the prototype exactly one verdict:
   - **promote** — the hypothesis held; retain the proven code and advance to the next unresolved
     risk;
   - **revise** — the goal still holds but evidence disproved the mechanism; remove or correct the
     failed mechanism before retrying;
   - **discard** — the prototype is unnecessary or outside the approved outcome; remove it.
6. Select the next prototype from the remaining observed gap. Candidate prototypes are not
   milestones and create no obligation to build them.

Keep the record compact: hypothesis, delta, real evidence, verdict, and remaining gap. Reuse an
existing task artifact or plan mechanism when one exists. This skill is the controller; do not
create a second task-specific controller, installer, or supporting documentation merely to run the
loop.

## Use the atomic capability protocol when required

When an approved implementation is one atom built through Development-Probe experiments, invoke
`$atom-building-machinery` as PDI's bounded protocol. PDI retains the approved envelope, adaptive
prototype loop, promotion decision, and completion responsibility throughout. Read the protocol's
`required_capability` and perform only that capability: Experiment Machinery comparison,
promotion, or real-path validation. Do not interpret `required_capability` as a lifecycle handoff;
every incomplete atom state returns `next_skill: prototype-driven-implementation`.

## Pull bounded internal support

Standalone planning directly inspects the declared real evidence and has no selectable controller.
During implementation, use only PDI's generated internal support projections:

- `references/research-support.md` for PDI-owned investigation of one blocking evidence question;
- `references/plan-support.md` for one observed delta that needs implementation-ready decisions;
- `references/write-code-support.md` for one approved product-code delta;
- `references/review-support.md` for PDI-owned inspection of one retained delta or the final accumulated surface.

Read a projection only when the current observed gap needs that capability. Supply the approved
outcome and envelope, prototype identity and observed gap, concrete evidence, exact support
question, and allowed scope or budget. Take back control after the projection returns its evidence,
conclusion, unresolved uncertainty, and recommended next delta.

Never let a projection widen scope, launch a successor phase or package, take lifecycle ownership,
or declare the implementation complete. A projection's recommendation is evidence for the
controller; it is not an automatic next milestone.

## Preserve the stable boundary

- Prototype through production seams rather than reimplementing product logic in a test harness.
- Fix the authoritative contract or architecture boundary when evidence points there; do not grow
  an exception list around observed manifestations.
- Retain only code that belongs in the final implementation. Temporary instrumentation is allowed
  when needed for proof, but remove it unless it remains useful operational telemetry.
- Use focused checks during discovery. After promotion, run the relevant regression surface.
- Before completion, use PDI's retained-surface support projection on the accumulated surface and run
  one end-to-end confirmation through the path the user will use.

## Stop and report

Complete only when the approved behavior works end to end, relevant failure behavior is proven,
the diff contains no discarded experiment, and a manual scope review passes.

Stop before:

- a new requirement or material scope expansion;
- a repository or path outside the envelope;
- commit, deployment, destructive action, credentials, or external communication;
- exhausted time or attempt cap;
- evidence that the approved outcome itself is incorrect or unsafe.

Report real milestones and deviations during execution, including the working agreement's maximum
progress-report interval. At completion, lead with the achieved behavior, then summarize each
prototype's verdict and the final verification. Do not make the user reconstruct the result from
the experiment history.
