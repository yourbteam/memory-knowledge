---
name: working-agreement
description: Use at the start of every Kamen Codex task, including projectless tasks, or whenever the user mentions the working agreement, directives, G-rules, playbooks, corpus memory, or memory-knowledge. Loads and follows all current canonical working-agreement directives, routes the task to the right playbook skill, and uses the memory-knowledge corpus only through MCP tools when available.
---

# Working Agreement

Use this skill to mirror the Claude working-agreement hook behavior in Codex.

## Canonical Files

- Directives: `/Users/kamenkamenov/memory-knowledge/working-agreement/DIRECTIVES.md`
- Corpus helper scripts: `/Users/kamenkamenov/memory-knowledge/working-agreement/`
- MCP wrapper: `/Users/kamenkamenov/memory-knowledge/scripts/mcp-remote-wrapper.sh`

Before substantive work, read the complete directives file and follow all current directives unless a higher-priority Codex system/developer instruction conflicts. Never encode a numbered G-rule range here; the canonical artifact may grow. Treat agent-specific wording such as "Claude" as applying to Codex in this environment.

For brief in-progress updates, apply the directives without a compliance header. For substantive responses use the compact canonical anchor: `directives=<artifact/revision>; mode=<mode>; controller=<active controller or none>; envelope=<approved|none|n/a>; scope=<scope>; exceptions=<none or conflict>`. The controller field names the playbook actually running (for Write-code, `prototype-driven-implementation`); envelope is `approved` only when its autonomy envelope was approved in-thread — `envelope=none` while editing product code is a self-declared G11 violation. Expand into a G-by-G audit only when Kamen asks, a conflict occurred, or unresolved compliance remains at closeout.

## Task Router

Classify the task and use the matching playbook when relevant:

- Research: `research-playbook`
- Plan: `plan-playbook`
- Write code: `prototype-driven-implementation`
- Review: `review-playbook`

For Write-code tasks, `prototype-driven-implementation` owns the lifecycle and pulls bounded
Research, Plan, Write-code, and Review support projections only when observed evidence requires
them. For standalone non-implementation tasks, retain the matching playbook above.

## Work-Memory Gate

Use the local-development fast path without `task-intake` for repository reads/searches,
approved file edits, repository-local formatting or generation limited to approved files,
diffs, linters, type checks, bounded unit tests, and local installation of an approved managed
artifact. The fast path is G26 preflight, the approved action, and direct verification only.

Invoke `task-intake` before crossing the governed operational boundary: deployments, remote
systems, databases or migrations, containers or images, authentication or secrets,
package/environment mutation, destructive cleanup, workflow drives, long live tests, a proven
recurrent command sequence, the same execution failure fingerprint twice, or a genuinely unclear
boundary. It must run the canonical classifier in `memory-knowledge/scripts/work_memory.py`;
prose classification is not a substitute. An operational receipt requires `sequence-runner`, a
receipt-backed selection, and `sequence_guard.py activate` before commands.

When a command fails, classify it under G20. Correct a first execution error immediately; invoke
`blocker-catalog` before fixing a deliverable blocker or a repeated execution error. Record a
qualifying correction, update the reusable sequence/script when behavior changed, and require a
fresh same-path successor verification before the correction becomes reusable. At substantive
closeout invoke `auto-capture`; only evidence-backed work lessons may enter candidate
review. Never persist people, preferences, diary/activity, transcript, or conversation
history as memory.

## Tier-2 Corpus

When the task asks about durable working-agreement knowledge, rationale, prior examples, or corpus entries, use the `memory-knowledge` MCP tools if they are available in the session.

Do not bypass the MCP with direct database, Qdrant, or ad hoc service writes. If the MCP tools are unavailable, say the corpus is not reachable from this session and ask before using any alternative.

Use `corpus-add` for one-at-a-time curated corpus writes.
