# Direction check — rebuilt atom surface ownership

The same empty-surface failure recurred across five rebuilds, so this atom compares the stable
boundary before implementation.

## Path 1 — carry the earliest verified baseline in code (selected)

The controller records an explicit supersession chain and copies the first run's hash-verified
baseline into every successor. This makes the atom's full change surface derivable by the same
`change-surface` and `record-promotion` code already used for one-run atoms. Cost: one start flag,
one small immutable chain record, and validation of every predecessor baseline.

## Path 2 — preserve operator ordering discipline

The operator delays canonical edits until the last rebuild, or manually restores a pre-atom tree
before each new `start`. This preserves the current controller but makes correctness depend on a
transcript-only ordering rule; the recorded `s12-approve-door` attempt 3 demonstrates that one
early canonical edit erases the surface. Cost: repeated rebuilding or manual tree manipulation,
with no machine-visible proof that the original baseline was used.

## Decision

Path 1 is the only path that makes immutable rebuilds and truthful accumulated surfaces coexist.
Path 2 is retained as the control in the deciding experiment and must reproduce the recorded empty
surface.
