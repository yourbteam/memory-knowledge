# Taggable Source Reload Sequence

<!-- BEGIN SEMANTIC INTAKE ENTRYPOINT -->
## Operator entry point

After selecting and activating this registered sequence, launch the shared controller with no
arguments:

```bash
python3 scripts/sequence_intake_launch.py
```

Answer only the semantic questions shown. Every question includes its response format, an example,
and constraints. The controller derives JSON, files, environment, flags, and argv; displays the
exact prepared operation; and requires a separate yes/no authorization before guarded dispatch.

Any argument-bearing commands below are machine-compatibility and verification evidence for the
deterministic adapter. Operators and agents must not construct or invoke those forms directly.
<!-- END SEMANTIC INTAKE ENTRYPOINT -->

## Purpose

Idempotently re-load one source's per-table CSV export into the consolidated MSSQL DB `taggable-dev`,
via the deployed `db-import` WebJob on `taggable-api-dev` — **no wipe**. New rows insert, changed rows
update, rows deleted-in-source stay in place. Proven on app→`system_record_id=1` (2026-06-26 and 2026-06-29).

The executable steps live in the checked-in script (kept as the automation this sequence calls):
`taggable-api:tools/Taggable.MigrationRunner/scripts/reload-source.sh`.

## Use When

- A weekly or ad-hoc re-load of an already-loaded source (app=1, app2=2, app3=3) from a fresh phpMyAdmin
  per-table CSV export.
- NOT for first-time onboarding of a brand-new source (that needs metadata/schema review first).

## Stable Boundaries

- **Idempotency boundary:** `LoadStagedTableWithRemap` MERGEs surrogate-identity tables on
  `(SystemRecordId, SourceId)` and natural-key tables on `(PRIMARY KEY + SystemRecordId)`. No
  `WHEN NOT MATCHED BY SOURCE DELETE` — deletes never propagate. So re-loads need **no wipe**.
- **Export filename contract:** blobs must be `<db>_table_<table>.csv` with a **single** `_table_`; the loader
  regex `_table_(?<t>[A-Za-z0-9_]+)\.csv$` extracts the table. phpMyAdmin export template must be `@DATABASE@`
  (NOT `@DATABASE@_table_@TABLE@`, which yields a double `_table__table_`; the script auto-corrects that).
- **Blob auth:** container `taggable-db-imports`; external data source `taggable_blob_ds` + scoped credential
  `blobcred` (SAS) — **SAS expires; refresh every run** (the June SAS were 12h/2-day windows).
- **WebJob:** `db-import` triggered WebJob on `taggable-api-dev`; `run.cmd` → `Taggable.MigrationRunner.exe`.
  A full-site deploy to `wwwroot` WIPES it — redeploy with `--redeploy-webjob` if absent.
- **DB tier:** scale `taggable-dev` to **S4** for the load (beats `LOG_RATE_GOVERNOR`), back to **S1** after.
- **Idle-kill:** app setting `WEBJOBS_IDLE_TIMEOUT=3600` must be set or Kudu kills the long load at 120s.

## Inputs

- `--export-dir` — folder of per-table CSVs (e.g. `~/Downloads/app.csv`).
- `--srid` — system_record_id of the source being reloaded (app=1).
- Optional `--redeploy-webjob` (if the WebJob was wiped), `--no-scale` (skip S4/S1).
- Default metadata: `taggable-database/Tasks/mssql-schema-migration/schema-load-metadata.json`.

## Preflight

1. `az login` present; .NET SDK on PATH; `taggable-api/tools/Taggable.MigrationRunner/appsettings.json` exists
   (holds the conn string; the loader resolves it from the `appsettings` sentinel arg).
2. Verify the export filenames parse to a single `_table_` (the script's stage step auto-fixes a double).
3. Confirm the `db-import` WebJob exists (else run with `--redeploy-webjob`).

## Steps (authoritative automation)

Run the script — it performs the whole flow and **scales the DB back to S1 itself** so the finish is not
session-dependent:

```bash
bash tools/Taggable.MigrationRunner/scripts/reload-source.sh \
  --export-dir <dir> --srid <n> [--redeploy-webjob]
```

It does: stage (+double-`_table_` fix) → [redeploy WebJob] → check WebJob present → clear+upload blobs →
refresh container SAS + ALTER `blobcred` → scale S4 → trigger `load-source-csv` → monitor to completion →
tail log → scale S1. Secrets are never printed.

## Failure Fingerprints

- **`<src>.<col> has no matching column in target <Table>`** → SOURCE COLUMN DRIFT. The app added a
  column; the loader maps CSV headers against the LIVE target schema and throws on the first
  unmapped one, aborting the whole reload ~6 min in with **zero rows loaded**. Happened three weeks
  running (2026-09-25 `order.donation_amount` + `donation_added_at`, 2026-10-01
  `users.password_set_at`, 2026-10-14 `payment.displayed_total`). **The script now refuses this in
  preflight, before the upload**, listing EVERY drifted column with its authoritative MySQL type and
  a ready-to-run `ALTER` — the runner's own error names only the first, which is why three separate
  weeks each revealed one column. Apply the printed statements (one at a time through MigrationRunner
  `query`; the apply-schema helper splits on `;\n`), record one dated file under
  `taggable-api/migrations/`, then re-run. An unmapped new TABLE is skipped harmlessly and is NOT
  this fingerprint.
- **Authoritative source types** come from the local MySQL mirror of the app database — container
  `taggable-mysql8`, database `taggable_dev`, port 3307 (override with `MYSQL_CONTAINER`/`MYSQL_DB`):
  `information_schema.COLUMNS`. Use it rather than inferring from the column name or the exported
  values: on 2026-10-14 all 94,609 exported payments had a NULL `displayed_total`, so no value
  existed to infer from and the name alone would equally have fitted a formatted string. The
  preflight does this lookup automatically; it still refuses on drift when the container is down,
  just without the type.

- **Every table skipped / `Staging done (0 tables)`** → double `_table__table_` filenames (wrong export
  template). Fix: rename `name.replace('_table__table_','_table_',1)` (script does this) or re-export with
  `@DATABASE@`.
- **`Login failed` / blob auth error on BULK INSERT** → expired SAS. Refresh the SAS + `ALTER ... blobcred`.
- **`db-import` not present** → WebJob wiped by a site deploy. Re-run with `--redeploy-webjob`.
- **Killed at ~120s "no output nor CPU"** → set `WEBJOBS_IDLE_TIMEOUT=3600`.
- **`Violation of PRIMARY KEY`** → should NOT happen post-fix; if it does, the deployed binary predates the
  natural-key MERGE — redeploy from `main`.
- **`WARNING: <tbl> has no usable primary key in the staged data (pk=[RowId])`** → expected for
  `PasswordResets` / `ProductLocationTimeSlot` (surrogate `RowId` not staged); they blind-INSERT and are NOT
  idempotent (would duplicate). Not a failure; tracked follow-up = MERGE them on their business key.
- **Script dies mid-monitor with `json.decoder.JSONDecodeError: Expecting value: line 1 column 1`** → a
  transient empty Kudu history response met an unguarded `json.load` under `set -euo pipefail`
  (2026-09-09, `blk-6d310140db00ab7c1ff2d797`). **The load is NOT affected** — it runs server-side and
  continues to completion. What is lost is the script's own tail + scale-back, so the DB is left on S4.
  Fixed in `reload-source.sh` by `poll_run()` (never fatal; the monitor retries on an empty id) plus an
  EXIT trap that waits for a terminal WebJob status before restoring S1 — it must never scale mid-load,
  which would sever the job's SQL connection. If running an older copy: read the real status from
  `$SCM/api/triggeredwebjobs/db-import/history` before assuming the load failed, then restore S1 by hand.

## Verification (pass signal)

- WebJob run **status = Success**, `CSV load complete (system_record_id=<srid>)` — read from the Kudu
  history/`output_log.txt`, which survives a local script death; the console tail does not.
- Natural-key proof: `OauthAccessTokens` count for the srid is **stable** (not doubled), no PK collision.
  Strongest form: compare the DB count per srid against the **source CSV line count** — on 2026-09-09
  `OauthAccessTokens`, `Users`, `PageViews` and `PersonProductImage` all matched their export exactly.
  `OrderProduct`/`Orders` legitimately exceed the export (rows deleted in source are retained here).
- Big tables (`OrderProduct`, `PersonProductImage`, `Users`, `PageViews`) grew **modestly, not doubled**.
- Other sources untouched (e.g. reloading srid=1 leaves srid=2/3 counts unchanged).
- DB tier back at **S1**.

## Closing the run (order matters)

The ledger accepts these ONLY in this order, and every step is refused once the run is terminal:

1. `work_memory.py verify --run-id <run> --outcome passed --quality <same-path|proxy> --evidence "..."`
   (add `--blocker-id` / `--correction-id` when the run exercised a corrected boundary). **Keep the
   returned `event_id`.** Use `same-path` only when THIS run drove the real corrected route; a
   reproduction is `proxy`.
2. `blocker_catalog.py transition --run-id <run> --blocker-id <blk> --to-status verified
   --verification-event-id <event_id from step 1>` — without that id it refuses
   `verification-event-id-required`, so step 1 can never be skipped or reordered after it.
3. `work_memory.py run-close --run-id <run> --result passed`.

**Close `failed`, not `passed`, on a run whose correction a later run must verify.** A successor is
bound with `select --verification-successor-of <run> --verifies-correction-id <id>`, and
`work_memory.py:3827` accepts a predecessor only when its `run_closed` carries `result=failed`.

**Fingerprint — `event-after-terminal`.** Recording verification after `run-close` (2026-09-16: the
reload that proved `blk-6d310140db00ab7c1ff2d797` same-path had its transition and verify run in the
wrong order, then the run was closed anyway). The evidence cannot be attached afterwards and the
blocker stays `fixed-awaiting-verification`; the run itself is unaffected. There is no repair once
the run is closed `passed` — it is neither amendable nor a valid successor predecessor — so the
next run of this sequence carries the verification instead.
