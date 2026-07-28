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

## Verification (pass signal)

- WebJob run **status = Success**, `CSV load complete (system_record_id=<srid>)`.
- Natural-key proof: `OauthAccessTokens` count for the srid is **stable** (not doubled), no PK collision.
- Big tables (`OrderProduct`, `PersonProductImage`, `Users`, `PageViews`) grew **modestly, not doubled**.
- Other sources untouched (e.g. reloading srid=1 leaves srid=2/3 counts unchanged).
- DB tier back at **S1**.
