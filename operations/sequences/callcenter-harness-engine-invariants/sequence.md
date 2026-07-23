# callcenter-harness-engine-invariants

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

**Use when:** modifying or auditing the `callcenter-harness` workflow engine (phase dispatch, ordering,
retry, or the ledger/state store) — re-run the invariant test before/after any engine change so the two
MAWF-derived mechanics below don't regress. Not a provisioning sequence; it's a fast, no-audio guard.

**Automation:** `callcenter-harness:scripts/test_engine_upgrades.py`. Run from repo root `~/callcenter-harness`.

## The engine in one paragraph
`WorkflowRunner.start()` loads a JSON workflow (a `phases` list), creates a `WorkflowRun`, and runs
phases, persisting `WorkflowRun`+per-phase `PhaseState{status,output,error,attempts}` to a JSON state
store after each phase. Phase behaviour is a hardcoded `if/elif` on `phase.type` in `_dispatch_phase`
(7 types: noop, audio_ingest, audio_redaction, transcription, prosody, call_path_classify, phase_ledger).
Data flows between phases via ad-hoc keys on `run.context` (NOT via `subscribes_to`). A review HOLD is
signalled by a handler setting `run.status` to a value in `TERMINAL_STATUSES={"skipped","blocked"}` and
returning WITHOUT raising. This is a minimized fork of `united-partners/src/up_harness`, a sibling of the
`mcp-agents-workflow` (MAWF) engine.

## Two invariants this guards (added cc-harness commit b02903a)
1. **`depends_on` is load-bearing (topological order).** `WorkflowDefinition.execution_order()` runs a
   STABLE topological sort of the declared graph; the runner iterates that, not raw list order.
   All shipped workflows are already topological, so order is unchanged — but a JSON reorder can no
   longer silently break data flow, and a **cycle / unknown depends_on / duplicate phase id raises
   before any phase runs** (fail-closed). `subscribes_to` is intentionally still declarative (only
   `depends_on` is honored) — do not "wire" it (phases pass typed Python objects via context, not text).
2. **Per-phase retry on a RAISED exception.** `max_attempts` resolves per phase from
   `phase.config.get("max_attempts", runner.default_max_attempts)` (default **1 = no retry**). The heavy
   STT/ffmpeg/parselmouth phases (`ingest/redact/transcribe/prosody`) opt into `"max_attempts": 3` in
   `workflows/callcenter-qa.json`. A **HOLD is never retried** (no exception raised); `attempts` is
   recorded on the ledger; a successful attempt clears the prior transient `error`.

## Steps
1. **Verify invariants (fast, no models/audio):**
   `PYTHONPATH=src python scripts/test_engine_upgrades.py` → `ALL ENGINE-UPGRADE UNIT TESTS PASS`
   (21 assertions: topo T1–T6 incl. all 5 workflows order-unchanged + cycle/unknown/dup raise; retry
   R1–R5 incl. HOLD-not-retried + attempts persisted).
2. **Real-path smoke (optional, needs the provisioned STT+redaction venv):**
   `PYTHONPATH=src python scripts/cc_redact_smoke.py ~/Downloads/audio-files/<call>.mp3` →
   `M3 redaction smoke: ALL PASS` (exercises ingest→redact through the topo+retry runner).

## Gotchas
- **Retry only fires on a raised exception.** Most redaction/transcription failures are HOLDs (handlers
  call `hold()` / set `run.status` and return) — those are terminal by design and must NOT be retried.
  If you add a new failure path, decide deliberately: raise (→ retry) vs HOLD (→ terminal review).
- **Adding a `PhaseState` field is backward-compatible** only with a default (`load()` does
  `PhaseState(**pstate)`; old state files lack new keys).
- **`max_attempts` guard:** `max(1, …)` prevents a 0/negative config from causing infinite retries.
- **Do not replace the `if/elif` dispatch with a plugin registry** or wire `subscribes_to` — those MAWF
  mechanics were deliberately NOT ported (7 stable phase types; typed in-process data). See the
  cc-harness-vs-MAWF analysis: only `depends_on` ordering + retry were worth bringing over.

## Failure fingerprints
- `T1 <workflow>: execution_order == list order` FAIL → the topo sort reordered a shipped workflow
  (a real behaviour change); a phase is listed before a same-tier independent it should follow.
- `R4 HOLD not retried` FAIL → a HOLD path started raising, or the terminal-status check moved inside
  the retry loop.
- `ValueError: dependency cycle / depends_on unknown / duplicate phase id` at start → a malformed
  workflow JSON (this is the intended fail-closed guard, not a bug).
