## Objective

Turn recurring failure patterns into reusable operational playbooks for next-step handling.

## Problem

Agent failure-mode summaries and finding summaries show repeated problems, but they do not yet produce standardized recommended responses.

## Intended Upgrade

Map recurring failure patterns to specific playbooks, such as:

- request clarification
- rerun retrieval/context assembly
- escalate to planning-first
- suppress low-value noise
- escalate to operator review

## Practical Before/After

Before:
- failure mode data exists but requires manual interpretation

After:
- the system can recommend the next best action for a known failure pattern

## Likely Surfaces

- playbook definitions linked to failure signatures
- repository-aware failure playbook lookup
- tighter relationship between findings analytics and operational response

## Current-State Grounding

- The repo already exposes workflow findings summaries, agent failure-mode summaries, triage confusion clusters, and convergence recommendations.
- Those surfaces already capture the underlying signals for repeated failures, but they stop at pattern reporting.
- The missing piece is a normalized playbook layer that turns those patterns into reusable response guidance that an orchestrator or operator can consume directly.

## Recommended Approach

- Add a read-only synthesis module that combines findings, convergence, and triage confusion signals.
- Normalize the outputs into stable playbook codes with confidence, evidence, and suggested actions.
- Keep the first version repository-aware and advisory only, without introducing a new persistence table.
