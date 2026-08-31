# Codex Working Agreement Setup

This repository is the authority for Kamen's personal managed Codex skills and working-agreement
state. A new machine must install from a clean, current `main` checkout; installed skill folders
are outputs, never sources.

OpenAI-provided system skills come with Codex, and plugin-provided skills come with their plugins.
Do not copy either class from another machine into the managed personal-skill root. This setup
installs the complete repository-managed set declared by `skills/managed-skills.txt` and preserves
every unrelated directory already present on the destination machine.

## Prerequisites

- A current Codex desktop app or CLI signed into Kamen's account.
- Git and Python 3.
- Node.js with `npx` on `PATH`; the repository's MCP wrapper uses `mcp-remote` through `npx`.
- This repository cloned on the office machine. Its location is not fixed.

Set task-specific paths for the current shell:

```bash
MK_REPO="/absolute/path/to/memory-knowledge"
MK_CODEX_SKILLS="${CODEX_HOME:-$HOME/.codex}/skills"
MK_BOOTSTRAP_STATE="${XDG_STATE_HOME:-$HOME/.local/state}/kamen-managed-skills"
MK_BACKUPS="${XDG_STATE_HOME:-$HOME/.local/state}/kamen-managed-skills/backups"
MK_REPORT="${XDG_STATE_HOME:-$HOME/.local/state}/kamen-managed-skills/office-parity.json"
```

## 1. Establish the canonical checkout

```bash
git -C "$MK_REPO" switch main
git -C "$MK_REPO" pull --ff-only origin main
git -C "$MK_REPO" status --short
```

The final command must print nothing. If it prints a path, stop: local repository changes must be
resolved before using this checkout as the installation authority.

## 2. Inspect the current machine without changing it

```bash
python3 "$MK_REPO/working-agreement/codex_office_bootstrap.py" status \
  --repo "$MK_REPO" \
  --codex-root "$MK_CODEX_SKILLS" \
  --report "$MK_REPORT"
```

`ready` means every managed skill already matches. `needs-install` is expected when skills are
missing or older. The report records each managed skill as matching, missing, or drifted and lists
unrelated installed directories that will be preserved.

## 3. Install or upgrade the managed skills

```bash
python3 "$MK_REPO/working-agreement/codex_office_bootstrap.py" install \
  --repo "$MK_REPO" \
  --codex-root "$MK_CODEX_SKILLS" \
  --state-dir "$MK_BOOTSTRAP_STATE" \
  --backup-root "$MK_BACKUPS" \
  --report "$MK_REPORT"
```

The bootstrap validates every canonical skill before mutation, creates a durable archive of any
pre-existing managed skill directories, runs the repository's recoverable transactional installer,
verifies exact projected hashes, and proves unrelated skill directories remained byte-identical.
An interrupted installer recovers from its journal on the next run. A failed validation changes
nothing.

The installer deliberately replaces older managed directories exactly. It never merges old and
new bytes, because merging can retain deleted scripts or stale instructions. The archive under
`$MK_BACKUPS` is the recovery source if an older local copy must be inspected later.

## 4. Configure the memory-knowledge MCP server

Generate the exact expected server specification for this checkout:

```bash
MK_NODE_BIN="$(dirname "$(command -v npx)")"
python3 "$MK_REPO/working-agreement/codex_office_bootstrap.py" mcp-spec \
  --repo "$MK_REPO" \
  --node-bin "$MK_NODE_BIN"
codex mcp get memory-knowledge --json
```

If the second command reports no server, add it:

```bash
codex mcp add memory-knowledge \
  --env "PATH=$MK_NODE_BIN:/usr/local/bin:/usr/bin:/bin" \
  -- "$MK_REPO/scripts/mcp-remote-wrapper.sh" \
  -y mcp-remote https://memory-knowledge.azurewebsites.net/mcp/
```

If an existing `memory-knowledge` entry differs, first preserve the whole Codex configuration,
then replace only that named MCP entry and run `codex mcp get memory-knowledge --json` again:

```bash
mkdir -p "$MK_BACKUPS"
cp "${CODEX_HOME:-$HOME/.codex}/config.toml" \
  "$MK_BACKUPS/config.toml.before-memory-knowledge-replacement"
codex mcp remove memory-knowledge
codex mcp add memory-knowledge \
  --env "PATH=$MK_NODE_BIN:/usr/local/bin:/usr/bin:/bin" \
  -- "$MK_REPO/scripts/mcp-remote-wrapper.sh" \
  -y mcp-remote https://memory-knowledge.azurewebsites.net/mcp/
```

The deployed endpoint is open and requires no copied token or credential. Restart Codex after an
MCP configuration change.

## 5. Refresh repository working-agreement projections

Preview the allowlisted trusted-project changes, then apply only generator-owned projections:

```bash
python3 "$MK_REPO/working-agreement/generate_projections.py" \
  --refresh-trusted --create-missing
python3 "$MK_REPO/working-agreement/generate_projections.py" \
  --refresh-trusted --create-missing --apply
```

The generator preserves every byte outside its owned fence and skips repositories not present on
the office machine. Projectless tasks use the globally installed working-agreement skill.

## 6. Verify the real operator path

Run the status command from step 2 again. It must return `ready` and the report must contain
`"parity": true`.

Then open a fresh Codex task and verify:

1. The `working-agreement` skill appears and is used at the start of the task.
2. A managed skill named in `skills/managed-skills.txt` can be explicitly invoked.
3. `/mcp` shows `memory-knowledge` connected.
4. A read-only memory-knowledge tool call succeeds.

Codex detects skill changes automatically; restart Codex if the refreshed skills do not appear.

## 7. Keep the office machine current

After each later pull of `main`, rerun steps 2 and 3. Do not enable this repository's tracked
`.githooks/post-merge` for a Codex-only office installation: that hook intentionally refreshes both
Codex and Claude. The office handoff package uses the explicit Codex-only bootstrap above.

## Repository-owned state used by this setup

- `skills/` and `skills/managed-skills.txt`: canonical personal skills and complete managed set.
- `working-agreement/client-skill-projections.json`: exact Codex projection hashes.
- `working-agreement/validate_skills.py`: source policy validation.
- `working-agreement/install_skills.py`: locked, journaled, transactional replacement.
- `working-agreement/project_client_skills.py`: source and installed parity verification.
- `working-agreement/codex_office_bootstrap.py`: office preflight, backup, install, report, and MCP specification.
- `working-agreement/generate_projections.py`: allowlisted repository `AGENTS.md` refresh.
- `scripts/mcp-remote-wrapper.sh`: stable memory-knowledge MCP launcher.
- `working-agreement/DIRECTIVES.md`: canonical working-agreement authority.
