# Work Memory

`events.jsonl` is the tracked sole canonical event authority and is atomically replaced
by `scripts/work_memory.py` when events are committed. `operations/blockers/BLOCKERS.md` is a
generated view and must never be edited as authority.

Only `work_memory.py transact` may commit ordinary event batches. Promotion stages
the pure `stage_event_batch` output inside its larger recovery journal.
