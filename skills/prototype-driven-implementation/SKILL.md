---
name: prototype-driven-implementation
description: Implement a concrete feature or root fix through a bounded, adaptive sequence of small runnable prototypes grounded in real code paths and captured real cases. Use when the goal is clear but important implementation behavior remains uncertain, a full implementation would make failures expensive to diagnose, or the user explicitly asks for prototype-driven implementation. Do not use for open-ended research, document-only planning, routine mechanical edits, or synthetic demonstrations that cannot exercise the production boundary.
---

# Prototype-Driven Implementation

Reach the approved user-visible goal through the fewest evidence-producing prototypes. Let each
observed outcome select the next unresolved risk; do not invent a complete prototype roadmap
upfront.

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
existing task artifact or plan mechanism when one exists. Do not create a controller, installer,
or supporting documentation merely to run the loop.

## Preserve the stable boundary

- Prototype through production seams rather than reimplementing product logic in a test harness.
- Fix the authoritative contract or architecture boundary when evidence points there; do not grow
  an exception list around observed manifestations.
- Retain only code that belongs in the final implementation. Temporary instrumentation is allowed
  when needed for proof, but remove it unless it remains useful operational telemetry.
- Use focused checks during discovery. After promotion, run the relevant regression surface and
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
