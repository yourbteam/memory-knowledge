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
