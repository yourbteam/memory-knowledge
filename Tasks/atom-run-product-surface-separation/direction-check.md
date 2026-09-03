# Direction check — atom run/product surface separation

## Goal distance

The controller currently accepts its run directory below an approved product path and then reports
its own request, baseline, and ledger as product changes. The goal is therefore `0 of 1`: the
product change surface is not mechanically isolated from controller output.

## Path 1 — sound approach, bounded ownership defect

Atom Controller already records a byte-level product baseline and derives an exact change surface.
The reproduced failure begins earlier: `start` accepts a run root that overlaps the approved
product tree. Rejecting overlap preserves the existing evidence model and makes its surface truthful.

## Path 2 — approach cannot reach the goal

If an external run root cannot complete the same controller lifecycle, the controller's evidence
model depends on co-locating machinery output with product files and the approach requires redesign.

## Verdict

Take additive Path 1. The real controller accepted the nested run and included three controller
files in the product surface, while existing controller journeys already run successfully from
external temporary roots. The verdict flips if the external-root captured case cannot complete
after the overlap refusal is introduced.
