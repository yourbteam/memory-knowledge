# secure-landing-seed

**Use when:** seeding the SECURE LANDING AREA with "original" call recordings for the callcenter-harness — the controlled zone the harness treats as the source of originals. Simulates ingestion by cloning audio from a source folder (e.g. `~/Downloads/audio-files`) into `~/.callcenter-harness/landing/`. The harness then treats each landing file as THE original; after a **verified-successful scrub** a separate cleanup deletes that original (+ raw ingest splits), so PII-bearing audio exists only transiently (Milestone 1: no PII persists).

**Automation:** `callcenter-harness:scripts/seed_landing.sh` (seed) + `callcenter-harness:scripts/scrub_and_retire.py` (scrub + retire original). Proven 2026-07-07 (5 files seeded + checksum-verified + idempotent; 1 file scrubbed → original + raw splits retired, compliant kept). Run from repo root `~/callcenter-harness`.

## Steps
1. **Seed** — `scripts/seed_landing.sh seed`
   Copies every `.mp3`/`.wav` from `$SRC` (default `~/Downloads/audio-files`) into `$LANDING` (default `~/.callcenter-harness/landing`), verifying each copy by SHA-256. Idempotent: a file already present with a matching checksum is skipped. Pass: `seed OK. N new file(s) …`.
2. **List** — `scripts/seed_landing.sh list` → shows the landing contents.
3. **Verify** — `scripts/seed_landing.sh verify` → `VERIFY PASS: all seeded files match their source` (checksum vs source; source-removed files are skipped, not failed).
4. **Scrub + retire** — `PYTHONPATH=src HF_HUB_OFFLINE=1 ~/.callcenter-harness/venv/bin/python scripts/scrub_and_retire.py [<file>|all]`
   Runs the pipeline on each landing original and, **only when redaction produced a verified `compliant.wav` and did NOT hold**, deletes the raw PII-bearing audio: the landing original + that run's raw `ingest/*.wav` splits. Keeps `redact/compliant.wav` (+ masked channels). Pass: `RETIRED <file> — scrubbed → …`; `DONE: N retired, M kept`.
   **Fail-closed:** if redaction HELD or produced no compliant recording, the original is KEPT (`[retire] KEEP …`) — never lose audio without a clean copy.

## Config (env)
- `SRC` — source of originals (simulated upload). Default `~/Downloads/audio-files`.
- `LANDING` — secure landing area (gitignored; under `~/.callcenter-harness/`, the air-gapped zone). Default `~/.callcenter-harness/landing`.

## Chain of custody (why this exists)
Original (PII-bearing) audio should live ONLY in the controlled landing zone, transiently. Flow: **seed → harness treats landing file as the original → run pipeline → on verified scrub success, delete { landing original + raw `ingest/*.wav` splits }, keep only `redact/compliant.wav`.** The deletion step is a separate, fail-closed cleanup (do NOT delete if redaction HELD).

## Gotchas
- **macOS bash 3.2:** the script avoids `mapfile` (bash-4 only) — uses a `while read` loop. Run with the system `bash` is fine.
- Seeding COPIES (originals in `$SRC` are untouched); in production `$SRC` would be the real ingestion source, not Downloads.
- The landing area is gitignored (never committed) — it holds PII-bearing originals.

## Failure fingerprints
- `no .mp3/.wav in <SRC>` → wrong/empty source dir.
- `checksum mismatch after copy` → disk/copy error (fail-closed; does not report success).

## Verification evidence (2026-07-07)
`seed` cloned 5 files into landing; `verify` → VERIFY PASS; re-run `seed` skipped all 5 (idempotent).

## Rollback
`rm -rf ~/.callcenter-harness/landing` (re-seedable from source).
