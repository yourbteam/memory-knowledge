# Internal Reproduce-First Support Contract

Use this contract only inside Prototype-Driven Implementation. It supplies one bounded verification
technique; it is not a selectable skill and never owns the implementation lifecycle.

## Invocation gate

Invoke only when all are true:

1. a recurring defect blocks the approved outcome;
2. the exact live failing state has been captured from the real path; and
3. the live verification point is far enough into an expensive run that repeated full runs would
   materially delay the fix.

A cheap one-off or a case without captured live failing state stays on PDI's normal direct
prototype proof.

## Build the tightest trustworthy reproduction

1. Preserve the exact failing inputs, state, and error classification.
2. Use the lowest boundary that still executes the same real code path:
   - call the real function or method in process;
   - boot the smallest real subsystem when component interaction is essential;
   - reserve the full live run for final confirmation.
3. Mock only true external edges. Never reimplement the behavior under test.
4. Prove red-before / green-after with unchanged captured inputs and an assertion that pins the
   practical answer, not merely the new mechanism.

The reproduction is untrusted unless it uses the same real code path, real captured inputs, and a
red-before / green-after transition caused by the intended fix.

## Confirm through the real path

After focused proof, run one closest valid live confirmation through the fastest real re-entry
point that exercises the changed behavior. A full run is required only when the question concerns
the whole chain. Treat a newly exposed failure as a new captured defect, not as evidence that the
proved correction failed.

Return the reproduction boundary, captured-input provenance, red and green evidence, live
confirmation result, and any newly exposed defect to PDI. PDI retains lifecycle control, selects
the next prototype, and alone decides promotion or completion.
