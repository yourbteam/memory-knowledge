# Work Memory

`events.jsonl` is the tracked sole canonical event authority and is atomically replaced
by `scripts/work_memory.py` when events are committed. `operations/blockers/BLOCKERS.md` is a
generated view and must never be edited as authority.

Only `work_memory.py transact` may commit ordinary event batches. Promotion stages
the pure `stage_event_batch` output inside its larger recovery journal.

## Late same-path verification

`work_memory.py verify-late` records a same-path audit only for a run that already has a
specific passed `run_closed` event and is the authenticated successor carrying the exact active
correction IDs. Supply each blocker/correction pair and an evidence artifact as JSON containing
`repository_key`, repository-relative `path`, and the expected `sha256`. The command rehashes
those evidence files and correction artifacts through the run's recorded repository roots, then
appends the audit plus the `fixed-awaiting-verification → verified → closed` transitions in one
ledger transaction. The original close event remains unchanged. Reusing the same audit event ID
with the same evidence is idempotent; a changed payload, stale artifact, missing transition, or
non-passed close is refused. Ordinary `verification_recorded` events remain invalid after run
closure.

For example, pass the exact already-recorded run-close event identity and one evidence artifact:

```sh
python3 scripts/work_memory.py verify-late \
  --run-id RUN_UUID \
  --target-run-close-event-id RUN_CLOSE_EVENT_UUID \
  --blocker-id BLOCKER_ID --correction-id CORRECTION_UUID \
  --evidence-artifact '{"repository_key":"united-partners","path":"Tasks/run/state.json","sha256":"EXPECTED_SHA256"}' \
  --evidence 'Describe the observed same-path result' \
  --late-reason 'Explain why verification followed the recorded close' \
  --event-id AUDIT_EVENT_UUID
```

## Archived UP history

The versioned archive under `legacy-up-20261018/` preserves selected UP events missing from the
current active ledger. Query recorded standing with `blocker_catalog.py historical-status` and
`--run-id` or `--blocker-id`. The result includes original event IDs, recorded audit/close
references, and any recorded evidence hashes. Its `authority` is `historical-record-only` and
`currently_proven_active_authority` is `false`: an archived `passed`, `verified`, or `closed`
entry reports what the old ledger recorded and does not establish current artifact state or
authorize a new transition. This read-only history path does not relax the active event schema or
lifecycle validator.
