# System Brittleness — Root Causes & Grounded Remediations

**Status:** Research (no code changes proposed here; this grounds a later hardening plan)
**Scope:** the memory-knowledge ingestion + job-dispatch system (PostgreSQL canonical · Qdrant vector · Neo4j graph · in-process async `JobDispatcher`)
**Method:** Causes are grounded **first-hand** in this repo's code (file:line) and two operational incidents observed directly. Remediations are grounded in an adversarially-verified web research pass (5 angles → 23 sources → 110 claims → 25 verified, 24 confirmed 3-0, 1 refuted). Where the cited sources do **not** cover our exact stack, the translation required is called out explicitly.

---

## Executive summary

The system is reliable on the **incremental happy path** (the four acute bugs that broke it this session are fixed). It is **not** reliable for **recovery, heavy operations, or partial failure** — and those are exactly the situations where a system's robustness is actually tested. The brittleness is structural, not incidental: jobs have no lease/heartbeat, multi-store writes are non-transactional and non-idempotent, the full-rebuild cutover happens only at the very end (so an interruption corrupts state), and there is no automated drift detection or durable resumability. Every one of these maps cleanly to a well-established, citable engineering pattern that the system does not yet implement.

Two incidents this session are the empirical evidence:

- **Incident A (dormant bugs):** four independent defects — dispatcher state-transition crash, a missing Qdrant `file_path` index (silent 0-chunk writes), B3 capacity overload, and Neo4j stale-connection aborts — all lay dormant for ~6 weeks and surfaced one-after-another on the first real ingestion. *No test or check caught any of them before production.*
- **Incident B (unrecoverable corruption):** an interrupted full re-ingest of `taggable-server` left **both duplicates and missing coverage**; recovering it required a hand-run offline script that **itself failed twice at the final step** (an external kill, then a Qdrant HTTP timeout) before a manual SQL `is_active` flip finished the job.

A subsequent systematic codebase audit (Part A2) confirmed these two incidents are **symptoms of a broader pattern**, not isolated bugs: ~45 additional grounded fragilities, several of which are *worse* than what we hit — the `repair` tool re-introduces drift, failed jobs never retry (dead code), runs report "success" on partial data, and Postgres/Qdrant carry the *same* connection-fragility class we just patched in Neo4j.

---

## Part A — Root causes (code-grounded)

| # | Fragility | Evidence in this repo | How it bit us |
|---|-----------|----------------------|---------------|
| A1 | **No job lease/heartbeat; recovery is startup-only** | `jobs/dispatcher.py:105` claims via `UPDATE … SET state_code='running'` with **no lease/heartbeat column**; recovery only at boot (`_reclaim_stale_running`, `dispatcher.py:59`). `config.py:86 job_orphan_timeout_seconds` is **defined but never referenced**. | A killed worker leaves a job `running` forever; a *hung* (not crashed) job is never detected at all. |
| A2 | **Deploy drain race** | Startup reclaim runs once; the draining old container can still claim jobs *after* the new container's reclaim (`stop()` drains in-flight tasks but nothing fences a late claim). | During a deploy, freshly-recovered jobs were re-orphaned by the draining old worker. |
| A3 | **Cutover/deactivation only at the *end* of a full run; not transactional** | `workflows/ingestion.py:1139` — "Step 8: Deactivate old points (only for full runs)" runs last. | An interrupt before Step 8 leaves new chunks written **and** old revisions still active → duplicates **and** (if coverage was partial) gaps. This is precisely the taggable corruption. |
| A4 | **No durable resumability for long/offline runs** | `_save_ingestion_checkpoint` is a **no-op when `job_id is None`** (`ingestion.py:161`); the offline rebuild path passes `manifest_job_id=None`. | A Qdrant HTTP timeout ~10 min into the rebuild discarded **all** progress; the run was all-or-nothing. |
| A5 | **Non-idempotent batch upserts** | `projections/summary_writer.py:90` `bulk_upsert_summaries … ON CONFLICT (entity_key) DO UPDATE` with **no pre-dedup** of the batch. | Cross-revision duplicate `entity_key`s in one batch → `ON CONFLICT DO UPDATE cannot affect row a second time`; summaries silently failed to write. |
| A6 | **No active-set drift detection/repair** | `integrity/compaction.py:65,74,85,99` only deletes rows **`WHERE NOT is_active`** (already-superseded). `integrity/repair_drift.py` only *re-projects* (additive upsert). | Neither tool reconciles **active** PG↔Qdrant divergence; we deleted ~19k orphaned Qdrant points **by hand**. |
| A7 | **Silent failure on missing infrastructure** | The missing `file_path` payload index made the per-file deactivate filter fail; the run still reported "complete" with 0 chunks written. | A whole class of incremental ingests silently no-op'd for weeks. (Index now created + asserted in `ensure_collections`.) |
| A8 | **Capacity: heavy ops infeasible in-system** | Shared B3 plan; embedding throughput ≈ 1 s/chunk; a full re-ingest of a large repo is multi-hour and OOMs under concurrency. | Large-repo rebuild is only feasible via a manual offline script — the brittleness the user flagged. |

> A1–A4 were *worked around manually* this session; A7 and the four acute Incident-A bugs are *fixed and deployed*. None of A1–A6/A8 are structurally closed.

---

## Part A2 — Codebase failure-mode audit (systematic sweep)

Part A was incident-driven. A four-subsystem audit (job orchestration · ingestion+projections · integrity/secondary workflows · DB/infra/auth) surfaced **~45 additional grounded fragilities**; the highest-signal are below, grouped by theme. The headline: several **"fix-it" and "success" paths are actively unsafe** — they corrupt or mask state rather than merely stall it, making them higher-priority than some Part-A items.

**T1 — Job lifecycle is not durable**
- `[HIGH]` **Retry & dead-letter are dead code** — `job_retry_manager.retry_failed_jobs` and `dead_letter_handler.move_to_dead_letter` have **no callers anywhere**; a failed job is terminal, so one blip past the 3 tenacity attempts strands a repo stale forever with no progression.
- `[HIGH]` **Retry cap is meaningless** — the dispatcher claim (`dispatcher.py:102-117`) never bumps `attempt_number` nor sets a per-run start timestamp; every run is "attempt 1" and there is no `started_utc` to detect a hung run.
- `[HIGH]` **Reclaim kills live work** — `_reclaim_stale_running` (`dispatcher.py:59`) marks **all** `running` rows failed at startup with no age/instance filter; under any overlap (deploy drain, future multi-replica) it kills a job another instance is actively running.
- `[HIGH]` **Non-atomic state machine** — `update_job_state` (`manifest_writer.py:58-97`) does read-then-write with no row lock; concurrent writers both pass `validate_transition`, so a terminal write can clobber a newer state.
- `[MED]` **No true mid-run resumability** — nothing persists an in-flight checkpoint during `execute_job`; resume starts from the enqueue-time checkpoint, re-running all work since enqueue. Also: semaphore acquired *after* the row is set `running` (widens the no-`started_utc` window); checkpoint JSON parse failures swallowed `except: pass` → silent restart-from-scratch.

**T2 — Multi-store writes leave cross-store divergence (no atomicity)**
- `[HIGH]` **Step 8 is 4 non-atomic deactivations** (`ingestion.py:1140-1148`); a crash between the Qdrant and PG deactivations leaves Qdrant with zero active old points while PG still marks them active — cross-store divergence, no checkpoint guarding the block.
- `[HIGH]` **Incremental ingestion has its own corruption window** — changed files are eagerly deactivated in Qdrant+PG inside the loop (`ingestion.py:631-696`) but replacements are upserted only at Step 6/7; a crash between leaves those files with **zero active chunks in both stores**, and incremental never reaches Step 8 to self-heal.
- `[HIGH]` **Partial Neo4j projection persists** — branch-head cutover + `complete_ingestion_run` (`ingestion.py:1298-1305`) are unconditional; a Neo4j Step-9 partial failure raises after the graph is half-populated, leaving stale CALLS/IMPORTS edges unpruned on a non-resumable retry.
- `[MED]` deleted-file path mutates 3 stores non-transactionally with Neo4j errors swallowed (`ingestion.py:631-651`); summary deactivation filters `commit_sha` only with **no `branch_name`** (`summary_qdrant.py:62-78`) → a full run on one branch blanks another branch's summaries.

**T3 — "Success" that isn't (silent partial completion)**
- `[HIGH]` `execute_job` records `completed` on `WorkflowResult.status != "error"` alone (`job_worker.py:60-80`); a workflow that swallows a sub-step failure marks a half-ingested commit authoritative — and the freshness scheduler then skips it as "unchanged."
- `[HIGH]` the per-file parse loop catches-and-continues; the run still reports `completed`/`success` and **advances the branch head even if every file errored** (`ingestion.py:625-823, 1298-1305`).
- `[MED]` summary batch dup-key `ON CONFLICT … cannot affect row a second time` logged per-row as warning while the run reports success (`summary_writer.py:106-121`) — the bug we hit, confirmed as a silent drop.

**T4 — The repair/integrity tooling is itself broken**
- `[HIGH]` **`repair` resurrects dead data** — Qdrant chunk repair fetches with **no `is_active` filter** and upserts everything `is_active=True`, never deactivating (`repair_drift.py:70-107`) — it re-introduces the drift it claims to fix and feeds stale code into retrieval.
- `[HIGH]` **`repair` can't deactivate prior-commit points** — point ID = `entity_key` embeds `commit_sha`, so latest-revision upserts write new IDs and never overwrite old-commit points (`repair_drift.py:103`); old points survive as active duplicates.
- `[HIGH]` chunk repair is scoped to the latest revision but **summary repair re-activates summaries across all revisions** (`repair_drift.py:116-124`) — inconsistent scoping leaves summaries fully un-pruned.
- `[MED]` `compaction` PG/Qdrant/Neo4j steps are independent, non-transactional, with no ingestion lock (`compaction.py:54-103`) → divergence if it dies mid-way or races ingestion.

**T5 — Connection & startup fragility (infra)**
- `[HIGH]` **Postgres has the same stale-connection gap Neo4j just fixed** — `init_postgres` (`postgres.py:39-44`) sets no `max_inactive_connection_lifetime`, liveness, or setup-ping; the first query after idle (hourly/weekly schedulers) fails with `ConnectionDoesNotExistError` instead of reconnecting.
- `[HIGH]` **Qdrant client has no `timeout`** (`qdrant.py:22-25`) — a hung connection blocks startup and every query indefinitely; this is exactly the `ResponseHandlingException` class that aborted the taggable rebuild.
- `[HIGH]` **Startup is not fault-tolerant** — `init_postgres` isn't try/excepted in lifespan (`server.py:5956`) so one transient PG error crash-loops the container; `dispatcher/scheduler/token-manager .start()` aren't wrapped (`server.py:6033`) so a start failure aborts startup **and leaks** the already-opened pools/tasks.
- `[MED]` Neo4j/Qdrant/git/embedding calls pass no timeout/retry and UNWIND/embed the whole repo in single unbatched calls; KV token refresh has no compare-and-swap (`credential_refresh.py:316,439`) → concurrent refresh can clobber the refresh token (permanent auth loss); per-DB `*_mode` overrides skip KV seeding (`server.py:5940-5954`).

**T6 — Read path assumes the stores agree**
- `[MED]` retrieval hydrates context by `entity_key` with **no `is_active` filter** (`retrieval.py:393-411`) — an entity active in Qdrant but superseded in PG is served as live evidence.
- `[MED]` `context_assembly._fetch_applicable_learned_rules` swallows all Neo4j+PG exceptions (`except: pass`) and the PG fallback ignores scope (`context_assembly.py:49-81`) — failures are indistinguishable from "no rules," and unrelated rules are always surfaced.

> These reorder the roadmap: **T4 (repair corrupts)**, **T1 dead retry/dead-letter**, **T3 success-on-partial-data**, and **T5 PG-liveness / Qdrant-timeout** are now top priority — they actively damage or hide state. (The Qdrant-timeout and PG-liveness gaps are the *same class* of bug as the Neo4j one we already fixed.)

---

## Part B — Grounded remediations (verified, cited)

Each failure mode maps to a canonical pattern. Confidence and vote are from the verification pass (3-0 = unanimous across three independent adversarial verifiers).

### B1 → fixes A1: Lease / visibility-timeout + consumer heartbeat  *(confidence: high, 3-0)*
A claimed job is made temporarily invisible (leased with a `leased_until`); if the worker doesn't complete it before the lease expires (crash, error, connectivity loss) it automatically becomes re-claimable — that *is* the orphan-recovery mechanism. For unknown/long durations the worker periodically **extends** the lease *only while actively working*, so a dead worker's lease lapses. Tune lease length to max expected processing time: too short → duplicate processing while the original still runs; too long → slow recovery. **Our-stack translation:** `SELECT … FOR UPDATE SKIP LOCKED` (already used) **+ a `leased_until`/`last_heartbeat` column + a sweeper** that returns expired leases to `pending`. Replaces the startup-only reclaim and closes the "hung job" gap.
Sources: AWS SQS visibility-timeout docs ([1]), SQS best-practices ([2]); PG-queue translation: brandur *Postgres queues* / *River* / *job-drain* ([3][4][5]).
*Trade-off carried from source:* at-least-once means a heartbeat **reduces but never eliminates** duplicates → downstream idempotency (B5) is mandatory.

### B2 → fixes A2: Fencing tokens + session/heartbeat ownership  *(high, 3-0)*
Issue a **monotonically increasing fencing token** on each lease acquisition; the protected resource persists the largest token seen and **rejects any write carrying a smaller one**, fencing off a stale/zombie worker (GC pause, slow drain, partition). Critically, **timeout-based revocation alone cannot guarantee mutual exclusion** in an async network — a slow worker is indistinguishable from a dead one, and two workers' in-flight writes can reorder. **Our-stack translation:** add a per-`(repository_key, shape)` token (e.g. a sequence/version) checked at write time — likely an application-side guard in Postgres, since Qdrant/Neo4j won't reject stale tokens natively (see Open Questions).
Sources: Hazelcast *Long Live Distributed Locks* ([6]); Kleppmann *How to do distributed locking* (originator of fencing tokens, DDIA Ch.9) ([7]).

### B3 → fixes A3: Blue-green rebuild with atomic alias cutover  *(high, 3-0)*
Build the new index in a **separate collection** in the background, then **atomically reassign an alias** from old→new. Because the alias swap is atomic, readers always see fully-old or fully-new — never the partial duplicate-plus-gap intermediate that late in-place cutover produces. An interrupted rebuild simply leaves the old collection serving. **Our-stack translation:** Qdrant supports this directly via collection aliases; **Neo4j has no verified equivalent** (see Open Questions) — emulate with versioned labels / a staging database / revision-scoped cutover. This is the single highest-leverage fix for the taggable failure mode.
Sources: Qdrant collections + aliases + embedding-model-migration tutorial ([8][9][10]); general blue-green reindex ([11]).
*Caveat from source:* atomicity covers the alias switch only; mind known peripheral alias bugs (not recovered on snapshot restore; silent overwrite of an existing alias target).

### B4 → fixes A6 (prevention): Transactional outbox + log-based CDC  *(high, 3-0)*
A naive dual-write (write Postgres **and** push to Qdrant/Neo4j separately) **cannot be atomic** — a crash between them drifts the stores. The **outbox pattern** writes an event row into an `outbox` table in the **same local transaction** as the canonical write (both commit or both roll back); **log-based CDC** (Debezium tailing the WAL) then streams committed events to **idempotent projectors** that apply them to Qdrant/Neo4j. Gives read-your-writes on the source and reliable eventual consistency for projections.
Sources: Debezium outbox ([12]); Confluent *dual-write problem* (Kafka vendor: no XA) ([13]); microservices.io *transactional outbox* (Richardson's canonical catalog) ([14]).
*Trade-offs:* requires a transactional DB (have it); duplicate events possible → idempotency required; eventual (not immediate) projection consistency; WAL/replication-slot bloat if CDC lags.

### B5 → fixes A6 (repair): Anti-entropy reconciliation via Merkle trees  *(high, 3-0)*
A **background** process that proactively **detects and repairs** divergence (vs. read-repair, which only fixes what's read). Compare canonical vs. projection by hashing ranges into a **Merkle tree** and descending only the divergent subtrees, so only differing ranges are re-projected. **Our-stack translation:** periodically hash ranges of active PG chunk/summary `entity_key`s vs. the Qdrant/Neo4j point/node sets; re-project only divergent ranges. This is the *automated* version of the manual reconciliation we ran. (`compaction` should also be extended to GC **active-but-unbacked** points, not just `NOT is_active`.)
Sources: anti-entropy/Merkle tutorial ([15]) corroborated by Cassandra repair docs ([16]) and Kleppmann/DDIA + the Dynamo paper.

### B6 → fixes A5: Client-generated idempotency keys (+ dedup-before-write)  *(high, 3-0)*
A unique client-generated key sent with the request; the server stores the key and the **first attempt's result (success *or* failure)** and replays it on any retry with that key, so side effects happen **at most once**. The key must be constant across retries but unique per logical operation (V4 UUID, or `workflowRunId+activityId`). Lets the projector **dedup the batch before upsert** — the direct fix for A5. **⚠ Refuted (1-2):** "retry on *any* error until it succeeds" is **unsafe** — a 500 is indeterminate and may need reconciliation, not naive retry.
Sources: Stripe API idempotency ([17]); Stripe engineering blog ([18]); brandur *idempotency keys* ([19]); Temporal ([20]).

### B7 → fixes A4: Atomic phases + recovery points / durable execution  *(high, 3-0)*
Two composable fixes for long, network-bound, interruptible operations: **(a) atomic phases + recovery points** (brandur): split the operation into phases of local ACID mutations *between* foreign calls, and persist a named checkpoint after each completed phase so a retry **resumes from the last checkpoint** instead of restarting. **(b) durable execution** (Temporal): event-sourced history replays completed activities from their stored results rather than re-running them. **Our-stack translation:** the checkpoint machinery **already exists** (`_save_ingestion_checkpoint`) but is disabled when `job_id is None` (A4) — making *every* run resumable (including offline/manual) is low-effort and would have saved the taggable rebuild from the Qdrant timeout. Adopting a full durable-execution engine is a larger, separate decision (Open Questions).
Sources: brandur *idempotency keys* (atomic phases/recovery points) ([19]); Temporal idempotency-and-durable-execution + event-history ([20][21]).

---

## Part C — Cause → fix → translation map

| Cause | Pattern (Part B) | Our-stack action | Effort |
|-------|------------------|------------------|--------|
| A1 stuck/hung jobs | Lease + heartbeat (B1) | `leased_until`/`last_heartbeat` columns + sweeper; wire the unused `job_orphan_timeout_seconds` | M |
| A2 drain race | Fencing tokens (B2) | per-shape version token, app-side guard in PG | M–L |
| A3 interrupted rebuild → dup+gap | Blue-green alias cutover (B3) | Qdrant aliases; revision-scoped/staged Neo4j cutover | L (highest leverage) |
| A4 no resumability | Atomic phases + recovery points (B7) | **enable checkpoints when `job_id is None`** | **S (quick win)** |
| A5 non-idempotent upsert | Idempotency keys / dedup-before-write (B6) | dedup batch by `entity_key` before `ON CONFLICT` | **S (quick win)** |
| A6 silent drift | Outbox+CDC (B4) prevention; anti-entropy (B5) repair | extend compaction to GC active-unbacked points; scheduled reconcile job | M (repair) / L (outbox) |
| A7 silent infra failure | (defensive) | startup assertion of required indexes; fail-loud on 0-chunk "success" | S |
| A8 heavy ops in-system | (capacity) | on-demand right-sized worker, or offline path made first-class + resumable (B7) | M |

## Part D — Suggested sequencing
1. **Quick wins (days):** enable checkpoints for all runs (A4/B7); dedup batches before upsert (A5/B6); startup index assertions + fail-loud on suspicious "success" (A7). These three directly close the two failure modes that bit the taggable recovery.
2. **Job durability (1–2 wks):** lease + heartbeat + sweeper (A1/B1), then fencing tokens for the drain race (A2/B2).
3. **Safe rebuilds (project):** blue-green alias cutover for Qdrant; design the Neo4j equivalent (A3/B3).
4. **Consistency (project):** scheduled anti-entropy reconcile (A6/B5) now; evaluate outbox+CDC (B4) and durable execution (B7-b) as the larger architectural step.

---

## Caveats (from the verification pass)
- **Vendor specificity / translation gap:** sources demonstrate patterns on SQS (leases), Qdrant (alias cutover), Debezium/Kafka (outbox+CDC), Temporal/Stripe (idempotency/durable execution). They are well-established and portable, but **do not directly cover our exact stack** — an *in-process* dispatcher (not SQS), Neo4j (no blue-green source found), and a Postgres-based queue. Mapping requires the translations noted above.
- **Idempotency is necessary, not sufficient:** at-least-once delivery and 500-indeterminacy mean idempotency is required *everywhere* but never a complete correctness guarantee alone; "retry until success" was **refuted**.
- **Eventual consistency:** outbox/CDC and anti-entropy give *eventual*, not immediate, projection consistency.
- **Currency:** patterns current as of 2025–2026; Kafka KIP-939 (limited 2PC) does not change the dual-write conclusion.

## Part E — Open questions resolved (2nd research iteration)

**E1 — Neo4j atomic cutover (was Open-Q1).** There is **no single documented atomic-swap primitive** like Qdrant aliases, but two viable patterns:
- **Database-alias swap (Enterprise / Aura only):** build the projection into a fresh database (`graph_vN`), keep clients on a stable alias, cut over with `ALTER ALIAS graph SET DATABASE TARGET graph_vN`. New transactions route to the new DB; in-flight ones against the alias are **aborted, not split**, and old/new live in physically separate DBs → no data-level half-state; rollback = repoint. *Caveats:* docs guarantee "safety" (concurrent txns aborted), not literally "atomic"; cluster/Aura propagation timing is **not documented as instant** (verify per topology); **not in Community Edition**; doubles storage during rebuild. ([22])
- **Community fallback — pointer-node revision flip:** write the new generation under a `revision`, flip a single `(:Projection {current:true})` pointer in **one small atomic transaction**, then GC the old generation. Requires every read query to filter on the pointer (easy to miss). Application convention, not officially-documented blue-green.
- **Do NOT** use `apoc.periodic.iterate` as the cutover — it commits **per batch** (not atomic across batches), exactly the partial-old/partial-new risk to avoid; fine for *building* the new DB ([24]). A single-transaction full relabel is truly atomic but bounded by transaction memory → only for small projections or the pointer flip ([25]).
- **Recommendation:** alias swap on Enterprise/Aura; pointer-node flip on Community. **Action item: confirm our Neo4j Aura edition/tier** — it determines availability.

**E2 — Concrete Postgres-queue lease mechanics (was Open-Q3).** Mature PG queues split into time-based (River/pgmq/Oban: a sweeper times out stale `attempted_at`/`vt`) vs heartbeat-based (Solid Queue: lease = "owning process pinged recently"). Because our job runtimes span **seconds → ~90 min**, a flat visibility timeout would have to be ≥ ~100 min (slow crash-detection for short jobs) — the **heartbeat model is the better fit**. Synthesized design (modeled on Solid Queue's 60s-heartbeat / 5-min-threshold + River/Oban rescue):
- Columns: `state`, `attempt`, `max_attempts`, `attempted_at`, `attempted_by`, **`leased_until`** (advanced by heartbeat).
- **Initial lease** `now() + 5 min`; **heartbeat every 30s** (`leased_until = now()+5min` while running — long jobs keep beating); **sweeper every 30–60s, single-leader** (advisory lock), returning `running AND leased_until < now()` → `available`, incrementing `attempt`, routing to `discarded` at `attempt >= max_attempts` (poison-job protection, enforced by both River and Oban).
- **Claim:** `SELECT … WHERE state='available' AND scheduled_at<=now() ORDER BY priority, scheduled_at FOR UPDATE SKIP LOCKED LIMIT n`, then `UPDATE … running` + set lease in the same txn.
- **Drain:** on SIGTERM stop claiming, keep heart-beating in-flight jobs, wait a bounded `shutdown_timeout` sized to the p99 *short* job (30–60s, **not** 90 min), then reset remaining to `available` before exit — a draining worker must never leave `running` rows or re-grab work. *Directly closes A1, A2, and the reclaim-no-age-filter audit finding (T1).*
- *Caveats:* pgmq's "30s vt" is illustrative (vt is a required arg); River Rescuer cadence unverified from docs; the 5-min/30s/30–60s numbers are a synthesis to tune to real runtimes. ([3][26][27][28])

## Open questions (remaining)
- **Q2 — Fencing-token enforcement** when Qdrant/Neo4j won't natively reject stale-token writes: likely an app-side guard/version table in Postgres checked at write time, and how that interacts with the outbox path. (For our current single-instance, `max_concurrent=1` deployment, lease+heartbeat+sweeper largely covers it; full fencing matters if/when multi-instance.)
- **Q4 — Durable-execution engine vs. atomic-phases-on-Postgres:** *leaning Postgres-first* — the audit (T1) shows the existing checkpoint/retry/dead-letter machinery is half-wired (dead callers), so wiring it up + lease/heartbeat is lower-risk than introducing Temporal/Restate, which can be re-evaluated once the basics hold.

## Sources
[1] https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html · [2] https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/best-practices-processing-messages-timely-manner.html · [3] https://brandur.org/postgres-queues · [4] https://brandur.org/river · [5] https://brandur.org/job-drain · [6] https://hazelcast.com/blog/long-live-distributed-locks/ · [7] https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html · [8] https://qdrant.tech/documentation/manage-data/collections/ · [9] https://qdrant.tech/documentation/concepts/collections/ · [10] https://qdrant.tech/documentation/tutorials-operations/embedding-model-migration/ · [11] https://widhianbramantya.com/elasticsearch/blue-green-deployment-in-elasticsearch-safe-reindexing-and-zero-downtime-upgrades/ · [12] https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/ · [13] https://www.confluent.io/blog/dual-write-problem/ · [14] https://microservices.io/patterns/data/transactional-outbox.html · [15] https://www.designgurus.io/course-play/grokking-the-advanced-system-design-interview/doc/antientropy-through-merkle-trees · [16] https://cassandra.apache.org/doc/latest/cassandra/operating/repair.html · [17] https://docs.stripe.com/api/idempotent_requests · [18] https://stripe.com/blog/idempotency · [19] https://brandur.org/idempotency-keys · [20] https://temporal.io/blog/idempotency-and-durable-execution · [21] https://docs.temporal.io/encyclopedia/event-history

*Open-questions research (E1/E2):* [22] https://neo4j.com/docs/operations-manual/current/database-administration/aliases/manage-aliases-standard-databases/ · [24] https://neo4j.com/docs/apoc/current/overview/apoc.periodic/apoc.periodic.iterate/ · [25] https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/ · [26] https://riverqueue.com/docs/maintenance-services · [27] https://github.com/pgmq/pgmq · [28] https://oban.hexdocs.pm/Oban.Plugins.Lifeline.html · [29] https://github.com/rails/solid_queue

*Verification: core remediations — 5 angles · 23 sources · 110 claims · 25 verified · 24 confirmed (3-0) · 1 refuted. Codebase audit — 4 parallel auditors over the job, ingestion/projection, integrity, and infra subsystems (~45 findings; high-signal subset above). Open-questions — 2 targeted research agents (Neo4j cutover, Postgres-queue mechanics).*
