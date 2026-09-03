# Direction check — blocker-aware atom closeout

The canonical Atom Controller currently declares an atom complete and authorizes its successor
solely from passed real-path case evidence. The canonical blocker catalog records operational
blockers, corrections, verification, downstream assignment, and terminal disposition, but no
event binds a blocker occurrence to the atom run and attempt that encountered it. Consequently,
the two controllers cannot prove that an atom has no unresolved or orphaned blocker occurrence.

The existing append-only ownership boundaries remain sound. The stable fix is a shared, read-only
closeout query over canonical blocker events: catalog opening derives immutable atom identity from
the Atom Controller run; validation preserves the query result; successor authorization reruns it
to catch later changes. A receipt-only declaration was rejected because it can be stale or forged
without consulting the canonical ledger.
