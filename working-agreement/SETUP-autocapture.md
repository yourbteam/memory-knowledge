# Auto-Capture Setup (Gap #2)

Two complementary mechanisms capture durable session lessons as **candidate** notes
(`verification_status='unverified'`) for later promotion. Both write via `author_repo_note`.

## Option 2 — skill (works in Claude *and* Codex, no extra cost)
Install `working-agreement/auto-capture.skill.md` into your AI client's skills (Codex: copy to `~/.codex/skills/auto-capture/SKILL.md`). At session
close the agent self-captures durable lessons. No setup beyond installing the skill.

## Option 1 — automatic Stop-hook + LLM extractor (Claude Code only)
A `Stop` hook runs `auto_capture.py`, which LLM-extracts lessons from the transcript and writes
candidates automatically. **Opt-in** (a per-session LLM call):

1. Enable it: `export MK_AUTOCAPTURE=1` (and optionally `MK_AUTOCAPTURE_MODEL=<chat model>`).
2. Register the Stop hook in `~/.claude/settings.json` (merge, don't replace):
   ```json
   "hooks": {
     "Stop": [
       { "hooks": [ { "type": "command",
         "command": "/Users/kamenkamenov/memory-knowledge/working-agreement/auto-capture-stop.sh" } ] }
     ]
   }
   ```
3. Restart Claude Code.

**Guarantees:** fail-open (any error → captures nothing, never blocks session end); does nothing
unless `MK_AUTOCAPTURE=1`; only writes to repos already ingested in the brain; never writes a
directive (candidates only). **Codex** has no session-end hook → use Option 2 there.

> Live note: the chat model must be one the codex token can call; if misconfigured the extractor
> simply captures nothing (fail-open). Verify once after enabling by ending a session and checking
> the repo's `repo_scoped_memory` for an `unverified` note.
