---
name: atom-assessment-machinery
description: Assess a completed atom against its fixed goal using saved build evidence, two focused model lenses and a structured final judgment. Produces proposed incremental interview updates; does not select or build the next atom.
---

# Atom Assessment Machinery

Run the bundled Python entry point. Python collects and verifies saved context; separate fresh model calls assess what changed, what remains, and overall completion. The final call directly fills the schema. Python saves a handoff and returns its path.

Default: Codex CLI, GPT-6 Astra, medium reasoning. Python 3.10+ and an authenticated Codex CLI are required. Override the bundled settings JSON to change model, reasoning, CLI path or timeout. Three calls per fresh run, no automatic retry. Obtain any required payload/destination permission before live calls.

For a connected cycle:

```bash
python3 scripts/atom_assessment.py start --root REPOSITORY --cycle CYCLE.json --run NEW_DIRECTORY
```

Paths to the script are relative to this skill directory. Cycle references provide the fixed goal, answer snapshot, selection, completed build and previous cycle's assessment when applicable. Incomplete or inconsistent references stop before model calls. Use `--prepare-only` to inspect collected context without calling models.

For an explicitly historical assessment, use `--historical-context CONTEXT.json` instead of `--cycle`. The context must preserve original source references and embedded content, assignment, pre-build state, completed build, current fixed goal and later interview background with historical boundaries. This mode does not pretend the historical build belongs to a new cycle.

Resume with `resume --run DIRECTORY`. Completed calls are reused only with unchanged prompts and outputs. An incomplete call requires inspection before a separately authorized new run; it is not retried automatically.

Inspect `state.json`, stage `events.jsonl`, and `handoff.json`. The handoff preserves both lens outputs and four final sections: achieved, remaining, goal_completion, interview_updates. Completion choices are established, not_established or cannot_assess. Structural validity is not a guarantee of judgment quality: assess whether findings preserve the evidence and its limits.

The handoff is a proposed update for the incremental interview. Do not mutate current answers, mark the goal complete, advance a cycle, or select another atom merely because this run completed. Preserve a completed atom separately from overall goal completion. Saved prompts, sources, model settings and results are the audit trail.

Final assessment evidence fields contain code-supplied IDs. The handoff’s resolved_evidence maps each selected ID to exact frozen-context pointers, character offsets and text, preserving duplicate locations. Python checks retrieval; the model remains responsible for whether the passage supports the claim.
