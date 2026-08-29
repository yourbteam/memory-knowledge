# Claude Code Setup — Working Agreement plumbing

This makes `working-agreement/DIRECTIVES.md` load into **every** Claude Code session, on
**every** project, on a machine. Repeat these steps on each machine (e.g. your office machine).

## What it does
A global `UserPromptSubmit` hook in `~/.claude/settings.json` runs `inject-directives.sh`
before each of your prompts. The script reads `DIRECTIVES.md` and injects it into Claude's
context, so the rules are consulted before Claude acts.

## Prerequisites
- `python3` on PATH (used to safely JSON-encode the directives). Check: `python3 --version`.

## Steps
1. **Clone/pull the repo** so the folder exists locally (e.g. `~/memory-knowledge`).
2. **Point the script at your path.** It defaults to
   `/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md`. If your repo lives
   elsewhere, either edit the `DIRECTIVES=` default in `inject-directives.sh`, or set:
   `export CLAUDE_DIRECTIVES_PATH=/your/path/working-agreement/DIRECTIVES.md`
3. **Make the script executable:** `chmod +x <repo>/working-agreement/inject-directives.sh`
4. **Register the hook** in `~/.claude/settings.json` — merge this block with the existing
   keys (do not replace the file):
   ```json
   "hooks": {
     "UserPromptSubmit": [
       { "hooks": [ { "type": "command", "command": "<repo>/working-agreement/inject-directives.sh" } ] }
     ]
   }
   ```
   Use the **absolute** path (no `~`).
5. **Restart Claude Code** (hooks are loaded at startup).

## Verify it works
- Run `<repo>/working-agreement/inject-directives.sh` directly — it should print one line of
  JSON containing the G1 text.
- In a fresh session in any project, ask: *"What does directive G1 say?"* — Claude should
  answer without you pasting anything.

## Notes
- The file is injected on every prompt, so keep it small — this is also directive **G1**.
- Codex plumbing will live in a separate `SETUP-codex.md` (added later).

## A3: repo-scoped memory hydration (optional)
A third `UserPromptSubmit` hook injects this repo's captured notes per prompt (closes the
capture→recall loop). Opt-in: set `MK_REPO_HYDRATE=1` and register the wrapper (absolute path):
```json
{ "hooks": [ { "type": "command", "command": "/Users/kamenkamenov/memory-knowledge/working-agreement/inject-repo-memory.sh" } ] }
```
Fail-open (any error/timeout/unknown-repo → injects nothing). Already wired in `~/.claude/settings.json`.


## Enforcement gates

Injection puts the rules in context; it cannot tell whether they were read or followed. Three
hooks close that, each added after a specific lapse on 2026-07-28. All three fail open — any
internal error lets the call or turn through, so a defect in a gate can never wedge a session.

| Script | Event | Refuses when |
| --- | --- | --- |
| `require-directives-read.sh` | `PreToolUse` | Any tool call before `DIRECTIVES.md` has been read at its current content in this session. Re-fires when the file changes or the read ages past 3h. |
| `deliver-trigger-rules.sh` | `PreToolUse` | A call matches a situation in `trigger-rules.json`. Delivers those rules' text, read live from `DIRECTIVES.md`, once per trigger per session. |
| `require-directive-anchor.sh` | `Stop` | The reply does not open with a well-formed G0 anchor, names a controller never invoked, declares `envelope=none` on a turn that edited files, or declares a word count below the real one. |

Register them alongside the injectors, in this order (absolute paths, merged into the existing
`hooks` block — `PreToolUse` runs the read gate then the delivery gate; `Stop` runs the anchor
gate).

`trigger-rules.json` is the delivery table: each entry names the tools it watches, a regex over
the tool input, the G-ids to deliver, and why that moment needs them. Setting `"on": "repeat"`
holds fire until the identical call is issued a second time, which is how G19's "same failure
fingerprint twice" is detected without waiting for the result. Rule text is never copied into
the table — it is read from `DIRECTIVES.md` at delivery, so it cannot go stale.

A Bash pattern is matched against the commands the line will actually run, not against its text:
heredoc bodies are dropped, quoting is respected, and each invocation is reduced to its program,
its flags, and its one real operand. So `grep run_client_regeneration` and a test fixture quoting
`git commit` do not match, while `cd /x && rm -rf y`, `bash -c "rm -rf y"`, and an env-prefixed
drive script do. A command that cannot be tokenized falls back to the raw string, so a parsing
gap under-blocks nothing. Set `"match": "raw"` on a trigger that genuinely wants the whole input.

Verify with crafted payloads rather than by inspection: pipe a `PreToolUse` JSON event into the
script with `MK_TRIGGER_STATE_DIR` pointed at a scratch directory, and check that a matching
call exits 2 with the expected rule headings on stderr while an unrelated one exits 0.

## Managed skills

Canonical personal skills are declared in `skills/managed-skills.txt` and bound to one parity
disposition each in `working-agreement/client-skill-projections.json`. The installed client
directories (`~/.codex/skills`, `~/.claude/skills`) are outputs, never authorities — never
hand-edit or hand-copy them.

1. **Validate and check-only first** (repository-local, mutates nothing):
   ```bash
   working-agreement/validate-skills.sh
   python3 working-agreement/project_client_skills.py check --client claude --installed-root "$HOME/.claude/skills"
   ```
   The check prints per-skill `MATCH`/`DRIFT`/`MISSING` states, reports unmanaged installed
   skills (always preserved), and fails closed when the canonical tree changed after the
   projection manifest was generated (regenerate with `project_client_skills.py generate`).
2. **Global installation is a separate, explicit approval.** After approval, install
   transactionally — every Claude-targeting mutation requires the complete reconciliation
   manifest and refuses on drift or missing dispositions:
   ```bash
   python3 working-agreement/install_skills.py \
     --source skills --manifest skills/managed-skills.txt \
     --target both --accept-cross-client \
     --reconciliation working-agreement/client-skill-projections.json
   ```
   The installer stages, locks, journals, exact-replaces only managed destinations, verifies
   post-install tree hashes, and recovers from its journal if interrupted.
3. **Fresh-session verification.** Open a new Claude session and confirm: the G0 anchor cites
   the current directives revision; a write-code request routes to `prototype-driven-implementation`;
   an operational request is code-classified by Working Agreement and routes through `sequence-runner` with zero-argument
   `scripts/sequence_intake_launch.py` intake.
4. **Rollback.** A failed or interrupted install restores from the transaction journal in
   `${XDG_STATE_HOME:-~/.local/state}/kamen-managed-skills`; rerunning the installer completes
   recovery before any new mutation.
5. **Refresh on pull.** Activate the tracked hook once per machine:
   ```bash
   git config core.hooksPath .githooks
   ```
   The post-merge hook then re-validates both client projections and refreshes both clients only
   when reconciliation passes; it fails visibly (and mutates nothing) on drift.
6. **CLI capability troubleshooting.** Host-agent execution probes the installed `claude --help`
   (see `skills/_shared/host_agent_runtime.py`); a missing required flag yields
   `CAPABILITY_MISSING` rather than a silent fallback. Record `claude --version` and re-probe
   after CLI upgrades.

Setup merges hook/settings blocks into `~/.claude/settings.json` structurally — never replace
the file, never print credentials, and override the repository location with env vars rather
than assuming a hard-coded user path.
