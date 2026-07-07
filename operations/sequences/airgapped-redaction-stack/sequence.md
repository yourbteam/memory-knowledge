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

## Failure fingerprints
- GLiNER `couldn't connect to huggingface.co` → mdeberta base not vendored; re-run provision.
- `STT venv missing at …` → run `airgapped-local-bulgarian-stt` provision first.

For the full harness end-to-end use `callcenter-harness-provision-verify`.
