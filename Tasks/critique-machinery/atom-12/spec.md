# Atom 12 — rebuilt atoms preserve their change surface

Frozen before canonical implementation. `frozen-red/` preserves the four real
`s12-approve-door` controller runs, each run's recorded Development-Probe evidence, the empty
surface produced by attempt 3, and the later accepted promotion evidence. The source runs under
`united-partners` remain unchanged.

## Supersession contract

`start --supersedes PREVIOUS_RUN` opens a new immutable run for the same `atomic_step_id` and
records an ordered, hash-bound supersession chain. The new run copies the earliest verified
change-baseline document in that chain as its own surface baseline. It refuses before creating a
run when the previous atom id differs, the previous run is complete, any chain baseline no longer
matches its ledger hash, the repository roots differ, or the new request changes `allowed_paths`.

The normal `start` behavior remains unchanged. Without `--supersedes`, a rebuild still captures
the current tree; this is the frozen control that produced an empty attempt-3 surface.

## Surface and closure

`change-surface` and `record-promotion` continue to use the run-owned baseline, which is now the
earliest baseline for a supersession chain. `status` prints the ordered chain from first run to
current run and whether it has been closed. Once the final run is complete, `authorize-next`
appends one hash-bound chain-closure event; repeated authorization is idempotent. A non-superseded
run retains its existing authorization behavior.

## Promotion boundary

Canonical changes are limited to Atom Building Machinery instructions and controller, its focused
tests, and the generated client projection registry. No united-partners file is edited. No model
call is needed for the experiment or operator validation.
