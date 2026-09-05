# Atom 15 direction check

This is the second failure in the same dependency class: the managed projection works while its
controller remains inside the repository that owns its support modules, then fails when installed
and invoked against another repository.

## Path 1 — preserve the existing architecture and bind the missing identities

- The native approval context, window, authentication reason, and signed payload all carry the
  atom id and exact request SHA-256. New receipts require both identities; the already-issued
  version-1 receipt remains a bounded, verified compatibility case for its own request.
- The managed installer writes one hash-bound canonical-source record into its own state directory.
  Installed controllers accept blocker closeout support only from that recorded repository and only
  when both required modules match the recorded hashes.
- Cost: one additional installed-state record and a versioned receipt validator.
- Stable boundary: approval identity is owned by the signed authorization contract; installed
  dependencies are owned by the managed installer.

## Path 2 — rebuild the controller as a self-contained projection

Copy blocker-catalog, work-memory, and all transitive dependencies into each client projection.
This removes the immediate missing-import failure, but forks central ledger ownership into two
installed bundles and makes every dependency change another projection synchronization problem.

## Verdict

Choose Path 1. It fixes each defect at the boundary that owns it without replacing the successful
native approval design or creating copied dependency drift. Flip to Path 2 only if a real managed
install cannot resolve and hash-verify one canonical source repository for both projections.
