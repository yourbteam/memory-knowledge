# airgapped-llm-judge

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

**Use when:** wiring the `callcenter-harness` command-mode eval (`execution_mode="command"`) to a **self-hosted, offline LLM judge** so script-adherence + emotion + active-listening are model-scored instead of the deterministic fixture. Runs fully offline via a loopback Ollama server (NFR-7: no external egress; loopback ≠ egress). **Depends on** the harness being provisioned (`callcenter-harness-provision-verify`).

**Automation:** `callcenter-harness:scripts/setup_airgapped_judge.sh` (provision) + `callcenter-harness:scripts/judge_ollama.py` (the `CC_HARNESS_AGENT_COMMAND` adapter). Proven end-to-end 2026-07-07 (qwen2.5:32b, air-gapped smoke ALL PASS on a real BG call). Run from repo root `~/callcenter-harness`.

## Steps

1. **Provision (ONLINE once):** `scripts/setup_airgapped_judge.sh provision`
   Installs Ollama (brew), starts the loopback server (`127.0.0.1:11434`), pulls `JUDGE_MODEL` (default `qwen2.5:32b`, ~19 GB). Pass: `provision OK. Judge model vendored; command-mode eval can run offline (loopback).`
2. **Self-test (offline):** `NO_PROXY=127.0.0.1 HTTPS_PROXY=http://127.0.0.1:9 scripts/setup_airgapped_judge.sh verify`
   → `VERIFY PASS: judge answered on loopback offline`.
3. **Run command-mode eval (offline) on a recording `<REC>`:**
   ```
   NO_PROXY=127.0.0.1 HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 \
     CC_HARNESS_AGENT_COMMAND="python3 $PWD/scripts/judge_ollama.py --model qwen2.5:32b" \
     PYTHONPATH=src ~/.callcenter-harness/venv/bin/python scripts/cc_command_eval_smoke.py <REC>
   ```
   Pass: `Command-eval smoke: ALL PASS` — `mode is command`, adherence + emotion + active_listening scored, `exact source-quote coverage true`, fail-closed HOLD when `CC_HARNESS_AGENT_COMMAND` unset.

## Contract the adapter satisfies (why judge_ollama.py is shaped as it is)
- Reads the judge prompt on **stdin** (`cc_harness.phase_ledger.prompts.judge_prompt`), returns JSON `{elements[{category,present,conveyed,evidence}], emotion{score}, active_listening{score}, notes}`.
- The evaluator (`evaluate_command`) is **strict/fail-closed**: every contract category must appear; a MET element (present ∧ conveyed≥0.5) needs `evidence` that is an **exact substring** of the transcript, else it HOLDs. The adapter repairs the model's near-miss quote to an exact source slice, or **downgrades** to not-met — never fabricates, never emits a met element with non-exact evidence.
- Executor gives **3 retries**, 180 s timeout; adapter exits nonzero on any failure → HOLD.

## Gotchas (discovered 2026-07-07)
- **Runtime must be Python-independent.** `llama-cpp-python` has **no cp314 wheel** (the harness venv is Python 3.14) — do NOT use it. Ollama (a Go/C++ binary) sidesteps this and keeps the model warm (no per-eval reload).
- **`format:"json"`, not a schema object.** Send Ollama `"format":"json"` (universally supported, guarantees valid JSON); rely on the prompt's OUTPUT_JSON_SHAPE + evaluator validation + 3 retries for keys. A version-specific JSON-schema `format` is an optional enhancement, not a dependency.
- **Loopback ≠ egress.** Set `NO_PROXY=127.0.0.1` so a dead-proxy air-gap test still reaches Ollama. The adapter talks ONLY to `127.0.0.1:11434`. `OLLAMA_HOST` should stay loopback (operator responsibility).
- **Cyrillic/UTF-8.** Emit JSON with `ensure_ascii=False`; evidence round-trips exactly for the substring check. (The old deterministic fixture actually JSONDecodeErrors on some Cyrillic evidence — the real adapter escapes correctly.)
- **Determinism:** `temperature=0, seed=0` for auditability (NFR-5).
- **Ollama tags** `qwen2.5:NNb` are already instruct-tuned (no `-instruct` suffix). On 128 GB, 32B Q4 (~20 GB) runs 100% on GPU; even 72B fits.
- **`num_ctx`** default 8192; adapter fails closed (nonzero exit) if the prompt would exceed 90% of it (no silent truncation).

## Failure fingerprints
- eval HOLDs `command-mode judge: CC_HARNESS_AGENT_COMMAND is required` → env not set (expected fail-closed).
- adapter `ollama call failed` → server not running; `setup_airgapped_judge.sh provision` (or `brew services start ollama`).
- eval HOLDs `evidence is not an exact source quote` → adapter repair bug; should be impossible (adapter downgrades). Investigate judge_ollama.py `_repair_evidence`.

## Verification evidence (2026-07-07)
Adapter unit tests 6/6; self-test PASS; `cc_command_eval_smoke.py` ALL PASS air-gapped (adherence 0.625, emotion 0.6, active_listening 0.3, exact-quote-coverage true, fail-closed HOLD). Real-model proof: 28.9 s inference (fixture 0.034 s), `ollama ps` = qwen2.5:32b 100% GPU, server log = model loaded on 127.0.0.1.

## Rollback
`brew services stop ollama; ollama rm qwen2.5:32b`. `CC_HARNESS_AGENT_COMMAND` unset → harness reverts to the deterministic evaluator.
