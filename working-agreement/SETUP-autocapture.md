# Auto-Capture Setup (Gap #2)

Two complementary mechanisms capture durable session lessons as **candidate** notes
(`verification_status='unverified'`) for later promotion. Both write via `author_repo_note`.

## Option 2 — skill (works in Claude *and* Codex, no extraction-model cost)
The `auto-capture` skill is a managed canonical skill (`skills/auto-capture/`). Install it into
**both** clients through the transactional installer — never hand-copy installed directories:
```bash
python3 working-agreement/install_skills.py \
  --source skills --manifest skills/managed-skills.txt \
  --target both --accept-cross-client \
  --reconciliation working-agreement/client-skill-projections.json
```
At session close the agent runs the installed `scripts/auto_capture.py --interview` in a PTY. The
script presents every finite choice as a numbered menu, rejects prose labels, maps the selected
numbers to canonical candidate fields, and performs the write. Free text remains free only for
the repository key, title, body, UUID, path, and revision.

## Option 1 — automatic Stop-hook + LLM extractor (Claude Code only)
A `Stop` hook runs the Claude installation of `auto_capture.py`, which LLM-extracts lessons from
the transcript and writes candidates automatically. The LLM receives the same five numbered
selection contexts. Code rejects prose labels and permits one corrected answer before failing
open. The hook invokes the installed Claude client through the existing Claude subscription;
it never calls the public Anthropic or OpenAI API SDK. **Opt-in** (one subscription inference,
or two only when correction is required):

1. Enable it: `export MK_AUTOCAPTURE=1`.
2. Register the Stop hook in `~/.claude/settings.json` (merge, don't replace):
   ```json
   "hooks": {
     "Stop": [
       { "hooks": [ { "type": "command",
         "command": "/bin/bash /Users/kamenkamenov/.claude/skills/auto-capture/scripts/auto-capture-stop.sh" } ] }
     ]
   }
   ```
3. Restart Claude Code.

The installed package can merge this command without replacing unrelated settings or hooks:
```bash
python3 ~/.claude/skills/auto-capture/scripts/install_claude_hook.py
```

**Guarantees:** fail-open (any error → captures nothing, never blocks session end); does nothing
unless `MK_AUTOCAPTURE=1`; only writes to repos already ingested in the brain; never writes a
directive (candidates only). Set `MK_AUTOCAPTURE_DRY_RUN=1` to print the normalized payload without
calling `author_repo_note`. **Codex** has no session-end hook → use Option 2 there.

> Live note: first verify with `MK_AUTOCAPTURE_DRY_RUN=1`; only then run one evidence-grounded
> capture and check the repo's `repo_scoped_memory` for an `unverified` note. The bounded probe can
> explicitly set `MK_CLIENT_KIND=codex` to exercise the Codex subscription path as well.
