# Direction check — atom evidence ownership

## Goal distance

Validation records now own their admitted bytes, but experiment and promotion events still reopen
caller-owned files on every status or authorization read. The atom is therefore not self-contained.

## Path 1 — sound approach, incomplete evidence ingestion

The validation snapshot already proves that event-specific, run-owned imports survive caller-file
mutation and remain tamper-evident. Applying the same ownership boundary to the earlier lifecycle
events completes rather than replaces the append-only controller model.

## Path 2 — approach cannot reach the goal

If importing only the artifacts the controller actually revalidates cannot reproduce the existing
experiment and promotion checks, the event model depends on external run structures and needs a
different durable-store design.

## Verdict

Take additive Path 1. Current tests prove external experiment and promotion mutation breaks state,
while the deployed validation snapshot survives the same mutation. The verdict flips if a minimal
run-owned import loses an existing integrity check or cannot resume after its caller sources vanish.
