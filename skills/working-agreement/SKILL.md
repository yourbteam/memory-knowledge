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

For brief in-progress updates, apply the directives without a compliance header. For substantive responses use the compact canonical anchor: `directives=<artifact/revision>; mode=<mode>; scope=<scope>; exceptions=<none or conflict>`. Expand into a G-by-G audit only when Kamen asks, a conflict occurred, or unresolved compliance remains at closeout.

## Task Router

Classify the task and use the matching playbook when relevant:

- Research: `research-playbook`
- Plan: `plan-playbook`
- Write code: `write-code-playbook`
- Review: `review-playbook`

If the task crosses modes, progress in order: research before planning when understanding is missing, planning before substantial implementation, and review after implementation.

## Tier-2 Corpus

When the task asks about durable working-agreement knowledge, rationale, prior examples, or corpus entries, use the `memory-knowledge` MCP tools if they are available in the session.

Do not bypass the MCP with direct database, Qdrant, or ad hoc service writes. If the MCP tools are unavailable, say the corpus is not reachable from this session and ask before using any alternative.

Use `corpus-add` for one-at-a-time curated corpus writes.
