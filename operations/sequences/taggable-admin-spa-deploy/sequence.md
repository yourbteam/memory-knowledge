# Sequence: taggable-admin-spa-deploy

Build the **taggable-admin-spa** (Vite/React) front-end and deploy its static `dist/` build to the
Azure Web App **`taggable-admin`** (RG `taggable`) via Kudu zip deploy. Use after merging admin-UI
changes (or any checkout you want live on the admin app). This is the SPA counterpart to
[`taggable-api-deploy`](../taggable-api-deploy/sequence.md).

Automation: **`taggable-admin-spa:scripts/deploy-admin-spa.sh`** — the script owns the exact steps;
prefer it over reconstructed commands.

## Preconditions
- `az login` done (`az account show` succeeds).
- Node.js + npm on PATH (build runs locally; verified with Node 24, app runtime is NODE 22-lts).
- On the taggable-admin-spa checkout you intend to deploy (usually `main`, pulled latest).

## Environment facts (why the script is shaped this way)
- Web App runtime is **Linux `NODE|22-lts`**; startup command is **`npx serve -s /home/site/wwwroot`**,
  i.e. it serves the pre-built static SPA from `wwwroot` (`serve -s` gives SPA client-route fallback).
- The app has **no app settings set**, so `SCM_DO_BUILD_DURING_DEPLOYMENT` is unset → **Oryx does not
  rebuild** on deploy. We build locally and push the finished `dist/` **contents**; served as-is.
- **`VITE_API_BASE_URL` is baked in at BUILD time** — `import.meta.env.VITE_API_BASE_URL`, read in
  `src/services/api_path.tsx`, used as a base with paths appended (e.g. `${API_PATH}/auth/admin/login`).
  The committed `.env` is `http://localhost:5078/api`, so the value **keeps the `/api` suffix**. The
  dev value is **`https://taggable-api-dev.azurewebsites.net/api`** (the script default).
- The script writes the value to **`.env.production.local`** (gitignored via `*.local`), which overrides
  the committed `.env` for the production build. It is not committed.
- `vite.config.ts` sets **`base: ""`** → relative asset paths (`./assets/...`), correct for `serve -s`.
- The zip deploy **replaces** `wwwroot` with the zip contents. There is **no WebJob** to preserve here
  (unlike taggable-api-deploy).
- **SCM/FTP basic-auth publishing is DISABLED** on `taggable-admin`
  (`basicPublishingCredentialsPolicies` `allow=false`), so a curl + Kudu username/password `zipdeploy`
  returns **HTTP 401**. The script deploys with **`az webapp deploy`**, which authenticates with the
  `az login` **Microsoft Entra (AAD)** token and works with basic auth disabled — **no** publishing-
  credential fetch. (Contrast taggable-api-deploy, whose target `taggable-api-dev` has basic auth
  enabled and uses curl `/api/zipdeploy`.)

## Steps
1. Activate + guard (registry discipline):
   ```bash
   cd "${MK_SEQUENCES_ROOT:-$HOME/memory-knowledge}"
   uv run python scripts/sequence_guard.py activate --sequence-id taggable-admin-spa-deploy \
     --sequence-doc operations/sequences/taggable-admin-spa-deploy/sequence.md
   ```
2. Run the deploy (env → build → assert baked URL → zip → zipdeploy → verify), from a
   taggable-admin-spa checkout:
   ```bash
   bash scripts/deploy-admin-spa.sh
   ```
   Override the API target when needed:
   ```bash
   bash scripts/deploy-admin-spa.sh --api-base https://taggable-api-dev.azurewebsites.net/api
   ```
   The script: preflights `az`/node/npm, writes `.env.production.local`, `npm ci` + `npm run build`
   (`tsc -b && vite build`), asserts the dev API base is baked in and localhost did not leak, zips
   `dist/` contents, deploys via `az webapp deploy --type zip` (AAD auth), then verifies.

## Verification / pass signal
- `az webapp deploy` exits 0 (script prints `deploy accepted`).
- Build produced `dist/index.html` and the bundle **contains** `https://taggable-api-dev.azurewebsites.net/api`
  (and **no** `localhost:5078`).
- `https://taggable-admin.azurewebsites.net/` returns **HTTP 200** and serves a Vite `index-*.js`
  asset (app serving the new build).
- Final line: `DONE: deployed taggable-admin from <branch> @ <commit>  (api_base=...)`.
- **HTTP 200 is necessary but NOT sufficient — a blank/crashed SPA still returns 200.** After deploy,
  do a real render check: load the site in a browser (or serve the built `dist/` with `serve -s` and
  read the console) and confirm `#root` is non-empty with no console `TypeError`. The script only
  proves the bytes are served, not that React mounted.

## Failure handling
- **`az webapp deploy` fails / HTTP 401** → 401 means SCM basic auth is disabled *and* the deploy tried
  basic creds; this script already uses AAD (`az webapp deploy`), so confirm `az account show` is a valid
  login with rights on RG `taggable`. Inspect `az webapp log deployment show -g taggable -n taggable-admin`.
  (A raw `curl -u user:pass .../api/zipdeploy` will always 401 here — basic auth is off by design.)
- **Build fails** (`tsc -b`/eslint/checker errors from `vite-plugin-checker` + `vite-plugin-eslint`)
  → fix the TypeScript/lint error in the SPA; the deploy is aborted before any push.
- **Baked-URL assertion fails** → the `.env.production.local` override did not take; confirm no
  higher-precedence `.env.production.local` content is wrong and that the var is `VITE_`-prefixed.
- **Site not serving new build after deploy** → check `$SCM/api/logs/docker`; the container runs
  `npx serve` on start — a startup/`npx` failure shows there. wwwroot was replaced, so roll forward.
- **Rollback** → `git checkout <prev-commit>` in taggable-admin-spa and re-run the script (roll forward
  to the previous build).

## Known build pitfall (fixed 2026-07-06)
- `vite.config.ts` `manualChunks` must **not** hand-split React-dependent libraries into their own
  chunks. An earlier config sharded `@fusioncharts/core` into ~20 `fusioncharts-lib-core-*` chunks and
  hand-split every vendor package; at runtime this threw `TypeError: Cannot set properties of undefined`
  (setting `__esModule` / `Children` / reading `forwardRef`/`createContext`) and the app rendered a
  **blank page** (HTTP 200, all assets loaded — so it passed the naive check). Fix: `manualChunks`
  coalesces **all** `fusioncharts` packages into one `fusioncharts` chunk and lets Vite/Rollup default
  chunking handle everything else. Do not reintroduce per-package vendor chunks.

## Notes
- Idempotent; safe to re-run. `--no-verify` skips the post-deploy checks (not recommended).
- `--api-base <url>` parameterizes the API target (default = dev, with `/api` suffix).
- No secrets are printed (Kudu creds are captured into shell vars only).
- Post-deploy runtime note (outside this sequence): the SPA calling `taggable-api-dev` cross-origin
  depends on taggable-api-dev CORS allowing origin `https://taggable-admin.azurewebsites.net`. Verify a
  real login if the API contract may have changed — this sequence only guarantees the correct build is
  deployed and served.
