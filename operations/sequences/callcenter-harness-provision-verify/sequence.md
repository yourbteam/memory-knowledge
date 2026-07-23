# callcenter-harness-provision-verify

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

**Use when:** standing up the full `callcenter-harness` call-QA harness on a fresh macOS machine (or re-provisioning) — vendoring **both** STT models (small + large-v3), the redaction/prosody stack, verifying offline, then live-verifying M2–M5 smokes and a **large-v3 real call** on a recording. Air-gapped compliance (NFR-7): provision is online-once; running needs no network.

**Composes:** `airgapped-local-bulgarian-stt` (STT venv + model) + `airgapped-redaction-stack` (PII/NER stack), then adds the QA smoke layer + large-v3 pipeline wiring that neither sub-sequence covers.

**Automation:** `callcenter-harness:scripts/setup_airgapped_stt.sh`, `callcenter-harness:scripts/setup_airgapped_redaction.sh`, `callcenter-harness:scripts/cc_*smoke*.py`. Proven end-to-end 2026-07-07 (both models, 7.3 GB, M1–M5 + large-v3 real call all pass).

**Prereqs:** macOS + Homebrew, git, Python 3.11+ (validated on **3.14**), ~6–8 GB free disk (Both models). A sample recording (`.mp3`/`.wav`, ideally 8 kHz stereo) — NOT in the repo, user-supplied. All commands run from the repo root `~/callcenter-harness` (the workflow loader uses a relative `workflows/` path — workflow.py:15).

---

## Steps

All provision steps ONLINE (download); everything else air-gapped.

1. **STT small** — `STT_MODEL=small ./scripts/setup_airgapped_stt.sh provision`
   Pass: `provision OK. Model vendored; inference can now run offline.` → `~/.callcenter-harness/models/faster-whisper-small/model.bin`.
2. **STT large-v3** — `STT_MODEL=large-v3 ./scripts/setup_airgapped_stt.sh provision` (idempotent; 2nd model into same venv) → `.../faster-whisper-large-v3/model.bin` (~2.9 GB).
3. **Redaction stack** — `./scripts/setup_airgapped_redaction.sh provision` (reuses the venv; hard-fails if venv missing — redaction.sh:23).
4. **Offline verify (no audio)** —
   - `PYTHONPATH=src python3 scripts/cc_smoke.py` → `M1 smoke: ALL PASS`
   - `./scripts/setup_airgapped_redaction.sh verify` → `VERIFY PASS: BG-NER + GLiNER loaded and ran offline`
5. **Live verify M2–M5** (on `<REC>`, model = small default). M2 under system python3; M3–M5 under the venv python with the dead-proxy air-gap:
   ```
   PYTHONPATH=src python3 scripts/cc_ingest_smoke.py <REC>
   env HF_HUB_OFFLINE=1 HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 \
     PYTHONPATH=src ~/.callcenter-harness/venv/bin/python scripts/cc_{redact,pipeline,eval}_smoke.py <REC>
   ```
   Pass: each `... ALL PASS`. A `held`/`skipped` is expected fail-closed behavior (low STT confidence / non-conversation / unidentifiable agent channel), not a failure.
6. **Large-v3 real call** — create a NON-committed variant `workflows/callcenter-qa-largev3.json` (copy of `callcenter-qa.json`) adding an **absolute** `stt_model_dir` to `redact-1.audio_redaction` AND a `transcription` block on `transcribe-1` (see Gotcha 2), then from repo root:
   ```
   HF_HUB_OFFLINE=1 PYTHONPATH=src ~/.callcenter-harness/venv/bin/python -c \
     'from cc_harness.engine.runner import WorkflowRunner; r=WorkflowRunner().start("callcenter-qa-largev3", {"recording_path":"<REC>"}); print(r.status, r.context.get("evaluation",{}).get("manager_summary"))'
   ```
   Pass: `status: completed`, all 6 phases, evaluation populated. Clean up with `rm workflows/callcenter-qa-largev3.json` (never commit it).

## Gotchas (corrections discovered 2026-07-07)

- **G1 · STT_MODEL must be explicit.** Script default is `large-v3` (stt.sh:27) but the harness default is `small` (stt.py:17) and the smokes expect small. A bare `provision` grabs the wrong 3 GB model and smokes report `STT model not vendored`.
- **G2 · Python 3.14 is fine — all deps are cp314 wheels.** `torch` 2.12.1, `ctranslate2` 4.8.1, `praat-parselmouth` 0.4.7, `faster-whisper` 1.2.1, `transformers`, `gliner` all install as prebuilt wheels on 3.14 — **no source build**. Verify with a binary-only dry-run (`pip install --dry-run --only-binary=:all: <pkg>`) in a real venv (system python is PEP-668 externally-managed and blocks the dry-run). If a future run finds no cp314 wheel, recreate the venv with 3.12.
- **G3 · large-v3 needs an ABSOLUTE `stt_model_dir` in a workflow FILE.** It cannot be passed via `WorkflowRunner.start(...)` inputs — `start` threads inputs into `run.context` only (runner.py:28); phase config comes solely from the workflow JSON (workflow.py:49-50). The knobs are `audio_redaction.stt_model_dir` (runner.py:112) and `transcription.stt_model_dir` (runner.py:195). A `~`-based path **FileNotFoundErrors** because stt.py:24 does not `expanduser` a caller-supplied `model_dir` (only the DEFAULT at :17 is expanded). Use `/Users/<you>/.callcenter-harness/models/faster-whisper-large-v3`. Smokes stay on small; only the real call is wired to large-v3.
- **G4 · GLiNER base encoder is required.** The redaction stack must vendor `microsoft/mdeberta-v3-base` or GLiNER phones home at load and the air-gap blocks it (caught by step 4's `verify`).
- **Benign warnings (not failures):** `roberta.pooler.* UNEXPECTED` keys on bg-ner load; an mdeberta tokenizer-regex notice.

## Failure fingerprints

- `STT model not vendored: …faster-whisper-small` → ran a bare provision (G1); re-run with `STT_MODEL=small`.
- GLiNER `couldn't connect to huggingface.co` → mdeberta base not vendored (G4); re-run redaction provision.
- Real call `FileNotFoundError: STT model not vendored: ~/...` → `~` path in `stt_model_dir` (G3); use an absolute path.
- `Unknown workflow: callcenter-qa-largev3` → not run from repo root, or variant file missing (workflow.py:15).

## Verification evidence (2026-07-07, recording 8 kHz stereo 94.3 s)

M1 ALL PASS; redaction `VERIFY PASS`; M2–M5 ALL PASS (2 PII spans masked, 53 prosody lines, adherence 0.125 / delivery flag `low_energy_delivery`); large-v3 real call `status: completed` (run `cc-run-2a37e83a58fb`), large-v3 use proven by config plumbing + ~100 s transcription runtime. Air-gap held (dead proxy 127.0.0.1:9 + `HF_HUB_OFFLINE=1`). Total footprint 7.3 GB; no source builds.

## Rollback

Full undo: `rm -rf ~/.callcenter-harness` (gitignored, re-provisionable). `rm workflows/callcenter-qa-largev3.json`. ffmpeg (brew) is harmless to leave.
