# Sequence: taggable-api-authed-endpoint-verify

Verify a **deployed taggable-api admin endpoint on dev** by logging in and calling it — the secret-safe,
repeatable way to live-verify any change touching an `[Authorize(Passport)]` API (e.g. the v3 report).
Promoted from discovery `2026-07-13-taggable-api-authed-endpoint-verify`.

Automation (worked example): **`taggable-api:scripts/verify-v3-report-scope.sh`** — copy/adapt it per feature.

## Why this sequence exists (the traps it encodes)
- Do **NOT** paste tokens into chat, and do **NOT** scrape credentials from the filesystem — the safety
  layer blocks credential scanning (correctly). The **sanctioned channel is an env file** the operator fills.
- I may not handle a plaintext password; sourcing it from the environment (never printed) is fine, exactly
  like `ConnectionStrings__TaggableDatabase`.

## Preconditions
- Feature deployed to dev (`taggable-api-deploy` sequence) and confirmed **in the deployed build via the
  swagger schema**, not just that the app restarted.
- `~/.taggable-verify.env` exists (OUTSIDE any git repo) with, filled by the operator:
  ```
  TAGGABLE_ADMIN_EMAIL=...
  TAGGABLE_ADMIN_PW=...
  ```

## Steps
1. Load creds **with auto-export** so subprocesses see them (the #1 trap):
   ```bash
   set -a; source ~/.taggable-verify.env; set +a       # plain `source` does NOT export -> python KeyError / login 400
   ```
2. Log in and capture the token (never printed):
   ```bash
   TOKEN=$(curl -s -X POST https://taggable-api-dev.azurewebsites.net/api/auth/admin/login \
     -H 'Content-Type: application/json' \
     --data-binary "$(python3 -c 'import json,os;print(json.dumps({"email":os.environ["TAGGABLE_ADMIN_EMAIL"],"password":os.environ["TAGGABLE_ADMIN_PW"]}))')" \
     | python3 -c 'import sys,json;d=json.load(sys.stdin);print((d.get("data") or {}).get("access_token") or "")')
   ```
   Login contract (from `AuthContracts.cs`/`AuthController.cs`): `POST /api/auth/admin/login {email,password}`
   → `AuthTokenEnvelope` → token at **`.data.access_token`**. 401 on bad creds.
3. Call the endpoint(s) with `-H "Authorization: Bearer $TOKEN"`; assert actual vs expected. Print only
   counts/status/bytes — never the token or creds.

## Verification / pass signal
- `login HTTP 200`, token acquired.
- Each case's actual matches expected (define per feature). For the v3 report scope filter, super-admin
  expected = **149 / 1 / 5 / 0 / 1** on `export-new-report-v3-optimized` (JSON row counts), and the
  `.xlsx` production endpoint returns 200 + a valid file.

## Failure handling / known traps
- **`KeyError` from `os.environ` + login HTTP 400** → sourced env not exported. Fix: `set -a; source …; set +a`.
- **Full-report `.xlsx` "500"** → almost always a client `--max-time` cap too short; the non-optimized V3
  handler takes ~220s for the full report. Use `--max-time 300`. Confirm with a narrow date range (fast 200).
- `login HTTP 401` → wrong creds in the env file (do not print them).
- Never widen scope: if a real endpoint bug appears, record it; don't silently "fix" it inside verification.

## Notes
- Secret discipline: token and creds are never echoed. The env file lives outside every git repo.
