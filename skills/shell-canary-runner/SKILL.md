---
name: shell-canary-runner
description: Run shell-based workflow canary wrappers that need live model/provider access, correct execution permissions, telemetry monitoring, phase-ledger inspection, loop diagnosis, convergence assessment, and constitution-grounded output-quality review. Use when Codex is asked to run a canary shell script, wrapper, threaded canary runner, live phase canary, or benchmark canary and report whether it failed, looped, converged suboptimally, or converged cleanly.
---

# Shell Canary Runner

## Core Rule

Run the requested shell wrapper as the source of truth. If live model/provider access is needed and the wrapper cannot provide network permission by itself, call the shell wrapper with `sandbox_permissions=require_escalated` on the `exec_command` tool and use a narrow `prefix_rule` for that wrapper path when appropriate.

Do not claim a wrapper can self-elevate network or filesystem permissions. Shell scripts can set their own environment; tool escalation is applied by the Codex tool call that launches the script.

## Before Running

Identify the exact wrapper path, requested worker count, mode, prompt/input file, and output root behavior from the script itself.

Read the relevant workflow YAML and phase id that the wrapper targets.

Read the software constitution document before judging final output quality. Use it to understand the intended job of the workflow and phase, not to invent extra requirements.

Check whether the wrapper already sets writable state homes, timeout, output root, and mode flags. If it does not, report the missing mechanical runner setup before running a long live test.

## Running The Canary

Run syntax validation first when the wrapper was edited:

```bash
bash -n <wrapper>
```

Run the wrapper exactly as requested. For live canaries that need provider access, use `exec_command` with:

- `sandbox_permissions`: `require_escalated`
- `justification`: short reason that the live canary needs provider/network access
- `prefix_rule`: the wrapper path, when safe and specific

Do not use tool escalation for mock-only runs unless the wrapper writes outside the workspace or otherwise requires it.

## Monitor During Run

Do not narrate progress from elapsed time alone. Poll or inspect evidence.

Monitor the wrapper output root and per-run files:

- `aggregate-summary.json`
- `run-*/summary.json`
- `run-*/canary-result.json`
- `run-*/stderr.log`
- `run-*/stdout.log`
- `run-*/telemetry-samples.json`
- copied `run-*/phase-ledger.json` when available

Monitor telemetry for:

- producer/verifier/critic start events
- completion events
- manager finding events
- status changes
- stagnant poll growth
- repeated verifier/critic cycles
- timeout markers
- provider/network/session errors

If telemetry shows a likely never-ending loop, advise killing the run. After kill, inspect the ledger and telemetry before proposing a fix.

## Ledger Review

For each run with a ledger, inspect the phase ledger, not only the aggregate summary.

Review the role sections separately:

- producer emitted records
- verifier emitted findings
- critic accepted findings
- critic rejected findings
- critic patches
- final manager-composed output

Review each role's history section when present. Identify which role changed what, which findings repeated, and whether the manager kept adding mechanical findings.

Do not diagnose persona quality from the final status alone.

## Outcomes

### Provider Or Runner Failure

If producer output is missing, first inspect stderr/raw output for provider, DNS, auth, session-directory, timeout, or JSON-extraction failures.

Report the concrete runner/provider failure. Do not call it a persona failure unless the model produced invalid persona output.

### Never-Ending Loop

If telemetry shows repeated cycles without convergence, advise killing the test run.

After kill, identify:

- first recurring finding
- role that keeps reintroducing it
- whether the manager is enforcing a mechanical rule or a persona is making an interpretive change
- exact ledger entries proving the loop
- smallest likely fix surface: runner, manager, producer, verifier, critic, or contract

### Converged But Not Optimal

If the run converges after many loops, still assess performance.

Use telemetry and ledger history to identify:

- number of producer/verifier/critic cycles
- which persona required repeated correction
- whether corrections were mechanical and should be handled by manager/contract
- whether corrections were persona judgment and need tighter persona instructions
- whether the loop count is acceptable for the phase risk

### Optimal Convergence

If the run converges cleanly, inspect the final manager-composed output.

Compare final output against:

- the phase's intended job from the constitution
- the phase's workflow YAML output context
- the phase's enum/detail contracts
- the source coverage policy
- the phase manager's composition behavior

Report whether the output is useful, correctly scoped, and ready to become a benchmark fixture.

## Report Format

Keep the report short and evidence-backed:

- command run
- output root
- pass/fail/converged/looped
- telemetry summary
- producer/verifier/critic record counts
- loop count or iteration count when available
- final output quality assessment
- exact blocker or next fix surface

Do not hide failed runs behind wrapper summaries. Include the decisive stderr, telemetry, or ledger evidence.
