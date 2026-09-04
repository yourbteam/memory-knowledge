# Atom 13 — validation atoms declare the field they validate

## Approved outcome

Every new atom request declares one `contract_surface` block. A renderer declares only
`{"kind":"render"}`. A validation atom declares its deliverable and an ordered nonempty `fields`
list; each field names its path, shape, and repository schema source. The allowed shapes are
`list`, `object`, `enum`, `integer`, `pinned-string`, and `prose`.

`start` resolves every declared field and source constant against the deliverable module in the
repository used for the run. Any prose target requires a completed code-controlled owner
interview. The interview presents hardcoded meanings for `waive` and `decline`; one operator word
adopts the complete statement beside it. A direct waiver block is refused. The accepted receipt
binds the exact request, field, repository, displayed meanings, operator choice, adopted waiver
statement, and date. The refusal names the field, the three recorded prose-parser failures, and
the two honest next actions: move the value into a structured field or complete that interview.

`record-experiment` performs a named static scan of each changed Python champion module and refuses
when any declared validation target is absent from its payload-key evidence. Extra observed keys
are reported as context, not treated as undeclared validation targets. The scan is stored with the
experiment event. It is explicitly heuristic evidence, not semantic proof.

`status` returns the immutable contract surface and waiver. New promotion receipts must carry the
same contract surface. Existing controller runs remain readable, but every new `start` requires the
new block.

## Frozen real cases

- The recorded proof-order and KPI requests are prose validation targets and refuse without a
  waiver.
- The recorded named-assigner request declares `ownership[].owner` as a pinned string sourced from
  `DOOR_FORM` and starts without a waiver.
- The recorded card-inside-phase request declares `activation_cards[].month` as integer and
  `activation_cards[].phase` as enum sourced from `ROADMAP_PHASES`, and starts without a waiver.
- A misspelled field refuses with the unresolved path and available schema keys.
- With an actual owner choice of `waive`, each prose request starts and `status` returns the exact
  displayed statement that choice adopted. `decline` keeps the request blocked.
- In the recorded round-three order, the first and third requests start and the prose-order request
  stops at start.

## Boundary

The canonical machinery changes only Atom Building Machinery, its tests, and generated client
projections. The separately authorized operator integration changes only
`Tasks/step6-feedback-closure/build_atom.py` so it preserves `contract_surface` and can pass a
completed waiver interview; it cannot copy a model-written waiver block. Existing Step 12
validation contracts, delivered pages, critique machinery, deployments, credentials, and model
calls remain excluded from Atom C itself.
