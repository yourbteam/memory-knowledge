# Sequence Discovery Log: taggable-admin-spa-deploy

Status: discovery
CreatedAtUtc: 2026-07-06T11:10:02Z
RegisteredSequenceMatch: none

## Intended Outcome

Build taggable-admin-spa with VITE_API_BASE_URL=https://taggable-api-dev.azurewebsites.net/api and deploy dist/ to Azure Web App taggable-admin (RG taggable, Linux NODE|22-lts, startup 'npx serve -s /home/site/wwwroot') via Kudu /api/zipdeploy

## Why This Looks Repeatable

SPA front-end for taggable-api-dev; will be redeployed on every admin UI change, mirroring the taggable-api-deploy sequence

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| Deploy via az webapp deploy (AAD) + verify live | az webapp deploy -g taggable -n taggable-admin --src-path bin/admin-spa.zip --type zip; curl https://taggable-admin.azurewebsites.net/assets/index-*.js | deploy accepted; site HTTP 200. Live bundle assets/index-C7_QaZHT.js contains https://taggable-api-dev.azurewebsites.net/api, zero localhost:5078. Promoted to operations/sequences/taggable-admin-spa-deploy/sequence.md + registry row. | Verified end-to-end on the public site; sequence is reusable |
| BLOCKER: curl+Kudu-creds zipdeploy -> HTTP 401 | curl -u user:pass --data-binary @admin-spa.zip https://taggable-admin.scm.azurewebsites.net/api/zipdeploy | HTTP 401. Root cause (confirmed): az resource show basicPublishingCredentialsPolicies scm -> allow=false on taggable-admin (vs true on taggable-api-dev). SCM basic-auth publishing is disabled. | G19 fix at the reusable boundary: switch script to 'az webapp deploy --type zip' which uses the az-login AAD token; works with basic auth disabled and needs no publishing-credential fetch |
| Prove prod env override + build bakes dev URL | printf 'VITE_API_BASE_URL=https://taggable-api-dev.azurewebsites.net/api\n' > .env.production.local; npm run build; grep -r taggable-api-dev.azurewebsites.net dist/assets | Build OK (built in 4.02s). dist bundle contains https://taggable-api-dev.azurewebsites.net/api; no localhost:5078 leak; index.html uses relative ./assets/. .env.production.local is gitignored (*.local) | Vite file precedence: .env.production.local overrides committed .env at build (mode=production) |
| Determine env var name + value shape from source | grep -rn VITE_API_BASE_URL src; cat .env | src/services/api_path.tsx:1 reads import.meta.env.VITE_API_BASE_URL; committed .env = http://localhost:5078/api. Value keeps /api suffix; dev value = https://taggable-api-dev.azurewebsites.net/api | G10: do not invent; verified against source |
| Identify target app + build fingerprint | az webapp list; curl https://taggable-admin.azurewebsites.net/ | taggable-admin (RG taggable, Linux NODE|22-lts, startup 'npx serve -s /home/site/wwwroot') serves the Vite build of taggable-admin-spa (title 'Taggable Admin', vite.svg, fusioncharts modulepreloads) | taggable-loader is an unrelated empty .NET app; taggable (RG API) is a stopped .NET v6 payments API |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
