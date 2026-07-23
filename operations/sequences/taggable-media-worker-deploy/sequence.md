# Sequence: taggable-media-worker-deploy

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

Deploy the **Taggable.MediaWorker** as a **continuous WebJob** on the Azure Web App
**`taggable-api-dev`** (RG `Umbraco`) — the background worker that drains pending `product_video`
rows and produces their FFmpeg renditions (720p transcode + watermark overlay + poster frame).
Use after deploying an API build that changes the media-upload/worker code, or to (re)deploy the
worker itself. This is a **separate** deploy from `taggable-api-deploy`; it does not touch the API
`wwwroot` or the existing `db-import` triggered WebJob.

Automation: **`taggable-api:scripts/deploy-media-worker.sh`** — the script owns the exact steps;
prefer it over reconstructed commands.

> **Status: PROVEN (first successful run 2026-07-07).** Deployed the continuous `media-worker` WebJob to
> `taggable-api-dev` (`WebJob deploy HTTP 200`), it reached **`Running`**, and it processed a real uploaded
> video **end-to-end**: `product_video` row went `pending → processing → ready` in ~20s with all 3 derived
> blobs (720p H.264 transcode + centered watermark overlay + poster frame) produced by the vendored win-x64
> ffmpeg, and the poll endpoint returned the URLs. Mirrors the proven `db-import` WebJob-PUT pattern in
> `reload-source.sh`, differing only in `continuouswebjobs` vs `triggeredwebjobs`.

## Preconditions
- `az login` done (`az account show` succeeds).
- .NET SDK on PATH: `export PATH=$HOME/.dotnet:$PATH`.
- **K1** — win-x64 `ffmpeg.exe` + `ffprobe.exe` present in
  `tools/Taggable.MediaWorker/ffmpeg/` (gitignored; the script fails loudly if missing).
- **K5** — the Azure App Settings for storage are set on `taggable-api-dev` (env vars override the
  empty committed `appsettings.json`): `ConnectionStrings__TaggableDatabase`, plus **5 per-version targets**
  `MediaUpload__Storage__{Original,Resized,Midsize,Watermark,Videos}__{AccountName,AccountKey,Container,PublicBaseUrl}`
  — containers on `taggableblobstorage`: Original→`images`, Resized→`resized`, Midsize→`midsizeimages`,
  Watermark→`watermark`, Videos→`videos`. (All set on `taggable-api-dev` 2026-07-07; persist across deploys.)
- **K3** — App Service **Always On** enabled (a continuous WebJob is killed on idle without it). Set via
  `az webapp config set -g Umbraco -n taggable-api-dev --always-on true`.
- **K10** — the `product_video` table exists (from `taggable-api:migrations/2026-07-07-add-product-video.sql`).
  Apply with a **GO-honoring** path — NOT MigrationRunner `apply-schema` (its `;\n` splitter shreds
  GO/BEGIN-END batches). **Confirmed method (2026-07-07):** split the file on `^GO$` and run each of the 4
  guarded batches as a separate `Taggable.MigrationRunner.dll query appsettings "<batch>"` call (each
  `IF…BEGIN…END` batch is one valid command); or `sqlcmd -i` / SSMS / Azure Query Editor.

## Environment facts (why the script is shaped this way)
- Host is the **same Windows .NET 8 Web App** as the API; the worker targets `net8.0` →
  **framework-dependent** `win-x64` publish.
- A continuous WebJob is deployed by **`PUT $SCM/api/continuouswebjobs/media-worker`** with a zip
  containing the publish output + `run.cmd` (`Taggable.MediaWorker.exe`) + the vendored `ffmpeg/`
  binaries. (Contrast the **triggered** `db-import` job at `.../triggeredwebjobs/db-import`.)
- Secrets are **not** committed or printed: DB + storage config come from Azure App Settings (K5);
  Kudu creds are captured into shell vars only.
- The ffmpeg binaries (~80 MB) are **not** in git — they are bundled into the publish zip at deploy.

## Steps
1. Activate + guard (registry discipline):
   ```bash
   cd "${MK_SEQUENCES_ROOT:-$HOME/memory-knowledge}"
   python3 scripts/work_memory.py classify --task-id "<task-id>" --operation-kind deploy --repeatable yes --meaningful-steps 3
   python3 scripts/work_memory.py select --task-id "<task-id>" --sequence-id taggable-media-worker-deploy
   python3 scripts/sequence_guard.py activate --task-id "<task-id>" \
     --sequence-doc operations/sequences/taggable-media-worker-deploy/sequence.md
   ```
2. Run the deploy (publish → bundle ffmpeg + run.cmd → zip → PUT continuous WebJob → verify), from a
   taggable-api checkout:
   ```bash
   export PATH=$HOME/.dotnet:$PATH
   bash scripts/deploy-media-worker.sh
   ```
   The script: preflights `az`/dotnet/zip and the ffmpeg binaries, `dotnet publish -c Release -r win-x64
   --self-contained false`, bundles `ffmpeg/` + a CRLF `run.cmd`, zips (no pdb), gets Kudu publishing
   creds, `PUT`s the zip to `/api/continuouswebjobs/media-worker`, then verifies status.

## Verification / pass signal
- WebJob deploy `HTTP 200` (or `201`).
- `GET $SCM/api/continuouswebjobs/media-worker` reports **`status: Running`** (a non-`Running` status
  means Always On is off — K3 — the script prints a WARN).
- Final line: `DONE: deployed continuous WebJob media-worker from <branch> @ <commit>`.
- End-to-end (manual, once K1/K5/K10 land): upload a video via `POST /api/media/upload`, confirm the
  `product_video` row flips `pending → processing → ready` with `UrlResized/UrlWatermark/UrlPoster`
  populated, and `GET /api/media/videos/status?guids=<guid>` returns `ready`.

## Failure handling
- **`missing win-x64 ffmpeg.exe/ffprobe.exe` (K1)** → drop the binaries in
  `tools/Taggable.MediaWorker/ffmpeg/` and re-run.
- **Deploy `HTTP != 200/201`** → check Kudu at `$SCM/api/continuouswebjobs/media-worker`; inspect
  `$SCM/api/logs/docker` (or the WebJob log) for a startup failure.
- **status not `Running`** → enable App Service **Always On** (K3), then re-check the status endpoint;
  the WebJob restarts automatically.
- **Worker starts but videos never leave `pending`** → check the WebJob log
  (`$SCM/vfs/data/jobs/continuous/media-worker/`) for FFmpeg binary-path errors (K1) or storage/DB
  config errors (K5) — the connection string / storage keys come from App Settings, not the zip.
- **Videos go `failed`** → the row's `Error` column holds the FFmpeg/exception message; `Retries`
  caps at 3. Fix the cause (bad ffmpeg build, wrong codec, storage perms) and reset the row to
  `pending` to reprocess.

## Notes
- Idempotent; safe to re-run (a re-`PUT` replaces the continuous WebJob). `--no-verify` skips the
  post-deploy status check (not recommended).
- Does not touch the API deploy or the `db-import` WebJob.
- Related: `taggable-api-deploy` (deploy the API itself), `taggable-source-reload` (the triggered
  WebJob PUT pattern this mirrors).
