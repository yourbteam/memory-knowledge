# airgapped-local-bulgarian-stt

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

**Use when:** set up a self-hosted, air-gapped Bulgarian STT env (ffmpeg + faster-whisper, vendored weights) and transcribe a call-center recording offline with no network egress (NFR-7). Provision is online-once; process/verify run air-gapped. Diarization comes from stereo channel-split, not a vendor.

**Automation:** `callcenter-harness:scripts/setup_airgapped_stt.sh` (+ `scripts/transcribe_airgapped.py`). Run from repo root `~/callcenter-harness`.

## Steps

Subcommands: `provision` (ONLINE) · `channels <audio>` · `process <audio>` · `verify <audio>` · `all <audio>` (all air-gapped after provision).

1. **Provision** — `STT_MODEL=<small|large-v3> ./scripts/setup_airgapped_stt.sh provision`
   Installs ffmpeg (brew), creates the shared venv `~/.callcenter-harness/venv`, installs `faster-whisper>=1.0` + `huggingface_hub>=0.23`, vendors `Systran/faster-whisper-<model>` → `~/.callcenter-harness/models/faster-whisper-<model>/`.
   Pass: `provision OK. Model vendored; inference can now run offline.`
2. **Verify offline** — `./scripts/setup_airgapped_stt.sh verify <audio>` → transcript + per-word timestamps with the network black-holed (dead proxy + `HF_HUB_OFFLINE=1`); `VERIFY PASS`. (Needs audio — `verify`/`process` run the model on a real file.)

## Gotchas

- **STT_MODEL must be explicit.** Script default is `large-v3` (stt.sh:27); the harness runtime default is `small` (stt.py:17) and the cc-harness smokes expect small. Always pass `STT_MODEL=`.
- **Python 3.14 OK — cp314 wheels exist.** `faster-whisper`/`ctranslate2` install as prebuilt wheels on 3.14, no source build (verified 2026-07-07). Confirm with a binary-only dry-run in a real venv (system python is PEP-668, blocks it).
- **Model dir is not `~`-expanded for callers.** A caller-supplied `stt_model_dir` (used downstream in the pipeline) must be an absolute path — stt.py:24 does not `expanduser` it (only the DEFAULT at :17). See `callcenter-harness-provision-verify` G3.

## Failure fingerprints
- `STT model not vendored: …faster-whisper-small` → bare provision grabbed large-v3; re-run `STT_MODEL=small`.

For the full harness (both models + redaction + M1–M5 + large-v3 real call) use `callcenter-harness-provision-verify`. Depends: the venv this creates is reused by `airgapped-redaction-stack`.
