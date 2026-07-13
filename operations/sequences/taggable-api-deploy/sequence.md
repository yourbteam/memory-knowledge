# Sequence: taggable-api-deploy

Deploy the **taggable-api** ASP.NET app to the Azure Web App **`taggable-api-dev`** (RG `Umbraco`) via
Kudu zip deploy. Use after merging changes to `main` (or any checkout you want live on dev).

Automation: **`taggable-api:scripts/deploy-api.sh`** — the script owns the exact steps; prefer it over
reconstructed commands.

## Preconditions
- `az login` done (`az account show` succeeds).
- .NET SDK on PATH: `export PATH=$HOME/.dotnet:$PATH`.
- On the taggable-api checkout you intend to deploy (usually `main`, pulled latest).

## Environment facts (why the script is shaped this way)
- Web App runtime is **.NET 8 (Windows)**; the API targets `net8.0` → **framework-dependent** publish.
- **No CI/CD, no run-from-package** on the Web App — manual `/api/zipdeploy` is the deploy path.
- `/api/zipdeploy` **merges** into `wwwroot` and **preserves** the `db-import` triggered WebJob under
  `wwwroot/App_Data/jobs/triggered/db-import`. The script fails loudly if that WebJob disappears.
- The DB connection string comes from the Azure App Setting **`ConnectionStrings__TaggableDatabase`**
  (an env var) which **overrides** the deployed `appsettings.json`; a clobbered appsettings.json is harmless.

## Steps
1. Activate + guard (registry discipline):
   ```bash
   cd "${MK_SEQUENCES_ROOT:-$HOME/memory-knowledge}"
   python3 scripts/work_memory.py classify --task-id "<task-id>" --operation-kind deploy --repeatable yes --meaningful-steps 3
   python3 scripts/work_memory.py select --task-id "<task-id>" --sequence-id taggable-api-deploy
   python3 scripts/sequence_guard.py activate --task-id "<task-id>" \
     --sequence-doc operations/sequences/taggable-api-deploy/sequence.md
   ```
2. Run the deploy (publish → zip → zipdeploy → verify), from a taggable-api checkout:
   ```bash
   PATH="$HOME/.dotnet:$PATH" bash scripts/deploy-api.sh
   ```
   The script: preflights `az`/dotnet, `dotnet publish -c Release` (net8.0), zips (no pdb), gets Kudu
   publishing creds, POSTs the zip to `/api/zipdeploy`, then verifies.

## Verification / pass signal
- `zipdeploy HTTP 200`.
- `db-import` WebJob still present under `App_Data/jobs/triggered/` (not clobbered).
- `https://taggable-api-dev.azurewebsites.net/swagger/v1/swagger.json` returns **HTTP 200** (app serving).
- Final line: `DONE: deployed taggable-api-dev from <branch> @ <commit>`.

## Failure handling
- `zipdeploy HTTP != 200` → read the deployment log at `$SCM/api/deployments/latest`; common causes:
  bad zip, locked files (retry), or an app-start failure surfaced on the next swagger check.
- **`db-import` WebJob MISSING after deploy** → a clean/sync deploy removed it. Redeploy it via the
  reload sequence's `--redeploy-webjob` path (`taggable-api:tools/Taggable.MigrationRunner/scripts/reload-source.sh`)
  or re-`PUT` the WebJob zip to `$SCM/api/triggeredwebjobs/db-import`.
- swagger != 200 after deploy → the app failed to start; check `$SCM/api/logs/docker` (or eventlog),
  usually a config/runtime-version mismatch. The prior wwwroot is overwritten, so roll forward with a fix.

## Notes
- Idempotent; safe to re-run. `--no-verify` skips the post-deploy checks (not recommended).
- No secrets are printed (Kudu creds are captured into shell vars only).
