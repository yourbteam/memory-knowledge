# Codex Working Agreement Setup

`working-agreement/DIRECTIVES.md` is the authority. Codex loads the globally installed
`working-agreement` skill at the start of every Kamen task, including projectless tasks.
Repository `AGENTS.md` projections provide an additional local copy at explicitly allowlisted
owned roots. The Tier-2 brain is accessed only through the configured `memory-knowledge` MCP.

## Install Managed Skills

Canonical directories are declared by `skills/managed-skills.txt`.

```bash
working-agreement/validate-skills.sh
working-agreement/install-skills.sh
```

The installer defaults to Codex. It serializes writers with a machine-wide lock, journals and
recovers interrupted transactions, replaces managed directories exactly, verifies hashes, and
preserves unrelated skills. Claude variants are not changed unless reconciled and explicitly
installed with `--target both --accept-cross-client`.

## Publish Repository Projections

Targets must be owned roots in `working-agreement/codex-projects.allowlist`. Preview first:

```bash
python working-agreement/generate_projections.py --refresh-trusted --create-missing
python working-agreement/generate_projections.py --refresh-trusted --create-missing --apply
```

For an exact allowlisted target that need not appear in Codex trusted-project config:

```bash
python working-agreement/generate_projections.py --create-at /path/to/repo/AGENTS.md
python working-agreement/generate_projections.py --create-at /path/to/repo/AGENTS.md --apply
```

Dry runs report `would-create`, `would-refresh`, or `skip(...)`; apply reports `created`,
`refreshed`, or `skip(...)`. Missing files are published without clobbering a file that appears
concurrently. Existing files are changed only when generator-owned, under a target lock, and all
bytes outside the generated fence are preserved.

Locks live under `${XDG_STATE_HOME:-$HOME/.local/state}/kamen-working-agreement-projections/`, keyed
by resolved target path, so serialized projection writes do not add files to project repositories.

Projectless tasks use the global skill. Do not create or depend on a parent `AGENTS.md`.

## Verify

```bash
working-agreement/validate-skills.sh
python working-agreement/generate_projections.py --refresh-trusted --create-missing
```

In a fresh projectless Codex task, the working-agreement skill should read all current directives,
emit the compact directive anchor for substantive responses, and select the matching playbook.
