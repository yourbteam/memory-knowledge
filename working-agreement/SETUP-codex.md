# Codex Setup — Working Agreement plumbing

This makes `working-agreement/DIRECTIVES.md` reach **OpenAI Codex**, so the same authoritative
directives govern Codex sessions as Claude Code. Repeat per machine.

## What it does
Codex has no per-prompt hook (unlike Claude Code's `inject-directives.sh`). Instead it loads
`AGENTS.md` from the working-directory tree. So we **project** `DIRECTIVES.md` into a generated
`AGENTS.md` next to where you run Codex. The brain is also reachable via the `memory-knowledge`
MCP server already configured in `~/.codex/config.toml`.

> Source of truth stays `DIRECTIVES.md`. The generated `AGENTS.md` is disposable — never edit it
> by hand; edit `DIRECTIVES.md` and regenerate.

## Prerequisites
- `python3` on PATH.
- The repo cloned locally (e.g. `~/memory-knowledge`).
- (Already present) `~/.codex/config.toml` → `[mcp_servers.memory-knowledge]` pointing at the
  canonical brain endpoint.

## Steps
1. **Generate the projection** into the directory where you run Codex (the repo root is the
   reliable, load-guaranteed location):

   ```bash
   python working-agreement/generate_projections.py --kind agents --write ./AGENTS.md
   ```

   This writes an `AGENTS.md` carrying the full directives plus a GENERATED header. Codex loads
   `AGENTS.md` from the repo tree, so the rules are in context before it acts.

2. **Keep it fresh.** Re-run step 1 whenever `DIRECTIVES.md` changes (wire it into the same
   post-commit path as `sync-corpus.sh`, or run it manually).

> **Per-project note:** to govern Codex in another repo, generate an `AGENTS.md` in that repo
> too. Only generate into repos you own; never overwrite a third-party repo's own `AGENTS.md`.
>
> **Repo already has its own `AGENTS.md`?** Don't overwrite it — merge instead:
>
> ```bash
> python working-agreement/generate_projections.py --kind agents --append-to /path/to/repo/AGENTS.md
> ```
>
> This folds the directives into a fenced `BEGIN/END GENERATED WORKING-AGREEMENT DIRECTIVES`
> block at the end of the file: the repo's own guidance is preserved, the directives land in
> Codex context, and re-running replaces only the block (idempotent — never duplicates or drifts).

## Verify it works
- `python working-agreement/generate_projections.py --kind agents` (dry-run) prints the
  directives with the generated header.
- In a fresh Codex session in that directory, ask: *"What does directive G1 say?"* — Codex
  should answer without you pasting anything.

## Notes
- A global `~/.codex/AGENTS.md` is **not** relied upon (its load behavior is unverified);
  per-repo `AGENTS.md` is the load-guaranteed path.
- The `CLAUDE.md` files become thin generated pointers via
  `generate_projections.py --kind claude-pointer`; Claude Code still gets the real directives
  through its `inject-directives.sh` hook.

## Capture (auto-capture skill)
Codex has no session-end hook, so capture runs via the **skill** (installed at
`~/.codex/skills/auto-capture/SKILL.md`, copied from `working-agreement/auto-capture.skill.md`).
At session close, invoke the `auto-capture` skill — it writes `unverified` candidate notes via
`author_repo_note` (functional on any registered repo now that A1+A2 removed the casing + ingested-revision
preconditions). Promotion stays human-gated ("lock it").
