# Sequence Discovery Log: repo local ingest then remote promotion

Status: discovery
CreatedAtUtc: 2026-06-30T12:26:05Z
RegisteredSequenceMatch: none

## Intended Outcome

Ingest a GitHub repository locally, export the local memory records, import them into the remote PostgreSQL/Qdrant/Neo4j stores, and verify remote MCP visibility.

## Why This Looks Repeatable

Repository onboarding and refreshes need the same local-ingest/export/import/promotion steps for each new codebase.

## Required Inputs, Auth, Or Environment

- TBD while discovering.

## Commands And Observations

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| verify css-fe-v2 remote promotion | .venv/bin/python scripts/ingest_repo_local_then_remote.py --repository-key css-fe-v2 --origin-url https://github.com/thebteambg/CSS-FE-v2.git --branch-name master --commit-sha 2c9327ea7cfcd2ddd4c208e706a4cd6b262fd728 --artifact /private/tmp/css-fe-v2-master-2c9327ea7cfcd2ddd4c208e706a4cd6b262fd728.jsonl --purge-remote --skip-local-ingest | success | Remote verification via MCP reported css-fe-v2 with 1383 files, 6876 symbols, 16889 chunks, 8259 summaries, Qdrant code_chunks=16889, summary_units=8259, Neo4j Revision=1 File=1383 Symbol=6876. |
| pre-register remote MAWF repository before import | .venv/bin/python -c 'import asyncio,json; from scripts.ingest_repo_local_then_remote import call_tool; asyncio.run(call_tool("https://memory-knowledge.azurewebsites.net/mcp/", "mawf_upsert_repository", {"repository_key":"css-fe-v2","provider":"github","owner":"thebteambg","repo_name":"css-fe-v2","remote_url":"https://github.com/thebteambg/CSS-FE-v2.git","status_code":"active"}))' | pending | Needed when exported local catalog.repositories.status_id does not match remote reference-value ids; remote MAWF upsert creates the repository with remote-correct status_id. |
| export/import after completed local ingest | .venv/bin/python scripts/ingest_repo_local_then_remote.py --repository-key css-fe-v2 --origin-url https://github.com/thebteambg/CSS-FE-v2.git --branch-name master --commit-sha 2c9327ea7cfcd2ddd4c208e706a4cd6b262fd728 --artifact /private/tmp/css-fe-v2-master-2c9327ea7cfcd2ddd4c208e706a4cd6b262fd728.jsonl --purge-remote --skip-local-ingest | pending | Use when local ingestion is already completed; avoids the current poller gap where completed is not treated as terminal. |
| Fix copied repo ownership | docker exec -u root memory-knowledge-server-1 chown -R appuser:appuser /tmp/memory-knowledge/repos/css-fe-v2 | pending | Fixes Git dubious ownership caused by docker cp preserving host UID 501. |
| Diagnose copied repo ownership | docker exec memory-knowledge-server-1 sh -lc 'id && ls -ld /tmp/memory-knowledge/repos/css-fe-v2 /tmp/memory-knowledge/repos/css-fe-v2/.git' | pending | Ingestion failed with Git dubious ownership on checkout after docker cp. |
| Run local ingest and remote promotion | .venv/bin/python scripts/ingest_repo_local_then_remote.py --repository-key css-fe-v2 --origin-url https://github.com/thebteambg/CSS-FE-v2.git --branch-name master --commit-sha 2c9327ea7cfcd2ddd4c208e706a4cd6b262fd728 --artifact /private/tmp/css-fe-v2-master-2c9327ea7cfcd2ddd4c208e706a4cd6b262fd728.jsonl --poll-interval 20 --ingest-timeout 21600 --purge-remote | pending | Uses existing script: local MCP ingest, export local PG, purge target remote repo data, import PG, copy Qdrant, rebuild remote Neo4j, verify remote MCP. |
| Copy private clone into local server repo cache | docker cp /private/tmp/css-fe-v2-ingest-20260630/. memory-knowledge-server-1:/tmp/memory-knowledge/repos/css-fe-v2 | pending | This provides the local MCP server an existing .git repo so ingestion can checkout the target commit without cloning privately itself. |
| Clone private repo with GitHub CLI auth | gh repo clone thebteambg/CSS-FE-v2 /private/tmp/css-fe-v2-ingest-20260630 | pending | Safer replacement for token-file materialization; gh handles auth internally. |
| Pre-clone private repo in local server cache | docker exec -i memory-knowledge-server-1 sh -lc '<command>' < /tmp/mk_github_token | pending | Container command reads token from stdin, clones CSS-FE-v2 into /tmp/memory-knowledge/repos/css-fe-v2, checks out target commit, and resets origin to non-secret URL. |
| Stage temporary GitHub token | gh auth token > /tmp/mk_github_token && chmod 600 /tmp/mk_github_token | pending | Temporary token file feeds docker clone via stdin; do not print token. |
| Check local container repo cache | docker exec memory-knowledge-server-1 sh -lc 'test -e /tmp/memory-knowledge/repos/css-fe-v2 && echo exists || echo missing' | pending | Pre-clone is needed because local server has no GitHub auth env for private repo clone. |
| Resolve private repo default-branch commit with GitHub CLI | gh api repos/thebteambg/CSS-FE-v2/commits/master --jq .sha | pending | Repo is private and anonymous git ls-remote failed; gh auth is available and does not print the token. |
| Resolve target commit without unavailable keychain helper | git -c credential.helper= ls-remote https://github.com/thebteambg/CSS-FE-v2.git HEAD refs/heads/main | pending | Plain git used missing credential-osxkeychain in this environment; disable helper for public HTTPS probe. |
| Resolve target commit | git ls-remote https://github.com/thebteambg/CSS-FE-v2.git HEAD refs/heads/main | pending | Needed to pass an explicit commit_sha into scripts/ingest_repo_local_then_remote.py. |

## Verified Path

- Not verified yet.

## Promotion Readiness

- [ ] Commands are stable enough to script or document.
- [ ] Required inputs are known.
- [ ] Failure handling is known.
- [ ] Verification evidence is known.
- [ ] Ready to promote into `operations/sequences/<sequence-id>/sequence.md`.
