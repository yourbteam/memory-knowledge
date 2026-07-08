# airgapped-redaction-stack

**Use when:** provision the offline PII-redaction + prosody stack (Bulgarian NER + GLiNER, vendored) into the cc-harness STT venv for the `callcenter-harness` S2 redaction stage. Detection runs offline (NFR-7). **Depends on** `airgapped-local-bulgarian-stt` (the venv must already exist).

**Automation:** `callcenter-harness:scripts/setup_airgapped_redaction.sh`. Run from repo root `~/callcenter-harness`.

## Steps

1. **Provision** — `./scripts/setup_airgapped_redaction.sh provision`
   Installs `gliner`, `transformers`, `torch`, `praat-parselmouth` into the STT venv; vendors `iarfmoose/roberta-small-bulgarian-ner` → `models/bg-ner/`, `urchade/gliner_multi-v2.1` → `models/gliner-multi/`, and (required) `microsoft/mdeberta-v3-base` into the HF cache. Hard-fails if the STT venv is missing (redaction.sh:23).
2. **Verify offline** — `./scripts/setup_airgapped_redaction.sh verify`
   Loads both NER models on synthetic Bulgarian text with the network black-holed. Pass: `VERIFY PASS: BG-NER + GLiNER loaded and ran offline`. No audio needed.

## Gotchas

- **GLiNER base encoder is required.** Must vendor `microsoft/mdeberta-v3-base` or GLiNER phones home at load and the air-gap blocks it. GLiNER config marker is `gliner_config.json` (bg-ner marker is `config.json`).
- **Presidio is NOT installed** despite the script header comment. PII detection is Presidio-*style* code (regex + checksum + NER union) in `cc_harness/audio/redact.py` — no Presidio package.
- **Python 3.14 OK — `torch` is a cp314 wheel.** `torch` 2.12.1 + `praat-parselmouth` 0.4.7 install as prebuilt wheels on 3.14, no source build (verified 2026-07-07). `gliner` pins `transformers` down (~5.6.x) in the combined install — the `verify` step proves bg-ner + GLiNER still load under it.
- **Benign load warnings:** `roberta.pooler.* UNEXPECTED` keys; an mdeberta tokenizer-regex notice. Neither affects `VERIFY PASS`.

## Recall hardening — long-transcript NER chunking (mandatory for long calls)

**Both NER models truncate a single forward pass** — bg-ner ~512 tokens, GLiNER 384 tokens (GLiNER logs
`Sentence of length … has been truncated to 384`). So a name/address/org spoken **late in a long call**
is silently dropped by the NER layer and leaks (the regex recognizers in `redact.py` cover the full text
but cannot catch a bare spoken name). Empirically: a name at char 5327 of a 5.4k-char transcript was
missed by both models and by `ner_spans()` — a real PII leak, invisible on short calls.

**Fix (in `callcenter-harness:src/cc_harness/audio/ner.py`, commit 29f5f08):** `ner_spans()` windows the
transcript via `_chunks(text, max_chars=600, overlap=150)` — whitespace-boundary windows, both models run
per window, each entity offset translated by the window's absolute start before unioning. Overlap ≥ any
realistic name+address so a boundary-straddling entity is whole in ≥1 window; latter-half space search +
hard-cap fallback bound the window count and guarantee termination. Short text (≤600 chars) → one window,
identical to the old single pass. Downstream `_merge_ranges` collapses the duplicate spans from overlap.

**Re-runnable verification** (from repo root `~/callcenter-harness`, STT venv python):
- `PYTHONPATH=src python scripts/test_ner_chunk.py` → `ALL NER CHUNKER UNIT TESTS PASS` (coverage,
  termination, boundary-entity-whole, short-parity, pathological bounded-window — no models needed).
- On a real long recording, masked-span count rises vs a truncated single pass (validated: `1783081158`
  7→13 spans, `9c93dc93` 6→10 spans, both `status=completed`).

**Gotcha:** the fix is char-offset (code-point) based; models return char offsets, so `base + ent["start"]`
is a correct absolute offset. Do NOT switch `_chunks` to byte offsets. Tune `max_chars` DOWN, never up
(recall bias): 600 chars ≈ 300–400 Cyrillic sub-word tokens, safely under GLiNER's 384.

## Failure fingerprints
- GLiNER `couldn't connect to huggingface.co` → mdeberta base not vendored; re-run provision.
- `STT venv missing at …` → run `airgapped-local-bulgarian-stt` provision first.
- **Long call, tail names unmasked / GLiNER `truncated to 384` warning** → NER chunking regressed or
  reverted; re-run `scripts/test_ner_chunk.py` and confirm `ner_spans` still calls `_chunks`.

For the full harness end-to-end use `callcenter-harness-provision-verify`.
