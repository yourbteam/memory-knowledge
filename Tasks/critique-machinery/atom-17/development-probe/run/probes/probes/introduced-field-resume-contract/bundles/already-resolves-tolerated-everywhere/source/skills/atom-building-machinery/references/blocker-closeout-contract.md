# Blocker closeout contract

Every blocker first encountered while one atom is active must be opened through
`scripts/blocker_catalog.py open --atom-run <atom-run>`. The catalog derives and records the
atom's step id, request SHA-256, immutable run id, and current experiment attempt. Callers do not
declare those identities.

Before Atom Controller records any real-path validation, it queries the canonical work-memory
ledger and snapshots the complete linked-occurrence summary into atom-owned evidence. A passed
validation completes only when that summary is clear. `authorize-next` queries the canonical
ledger again so a blocker opened after validation still prevents the next atom.

A linked occurrence is clear only when one of these code-checked dispositions applies:

- `closed`, with `remaining_work` exactly `none`;
- `non-gap`, with recorded classification evidence;
- `superseded`, with an existing successor blocker occurrence bound to the same atom;
- still `open` only when classified `incidental-system-defect` and assigned to one nonempty
  downstream owner.

An open deliverable blocker, `fixed-awaiting-verification`, `verified`, a broken supersession, or
any unknown disposition blocks completion. `verified` is intentionally nonterminal: it must still
be closed with no remaining work.
