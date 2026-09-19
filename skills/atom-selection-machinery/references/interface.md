# Configuration and output

Input is a completed Input Interview Machinery JSON: a nonempty `questions` list,
unique `question.id` values, and nonempty `final_answer.answer` strings. Each
question's `answer_status`, if supplied, must be `answered` (canonical interview
export) or `ready` (saved selector projections). Its `final_answer.self_assessment.choice`,
if supplied, must be `ready`; top-level `status`, if supplied, must be `completed`. Existing
frozen context projections omitting those outer statuses are supported. All answer
content, quotations, limits and other supplied fields are preserved for the models.

The input belongs to the caller. The package contains no Taggable baseline or fixed
ten-question template. Other tasks supply their own completed interview and delivery
goal. Store runs outside the installed skill directory.

`settings.json` has four fields:

```json
{
  "model": "gpt-6-astra",
  "reasoning": "medium",
  "cli": "/Applications/ChatGPT.app/Contents/Resources/codex",
  "timeout_seconds": 300
}
```

The CLI path may be an installed executable name. It must support Codex's existing
structured-output interface. Alternative models are configurable through that CLI;
other providers are not silently adapted. Defaults apply equally to the six calls.

`prompts.json` contains four ordered `lenses` (each with `id`, `name`, `prompt`),
`selection`, and `distillation`. Each call is independent; no conversation history
is assumed. Code supplies the complete context and accumulated outputs where needed.
No separate paid assessment call is added.

The run retains frozen inputs/configuration, their hashes, every attempt's prompt,
schema, invocation, events, answer and completion evidence. `state.json` records
completed stages. `selection.md` is the comparison and original proposal;
`atom.md` is the final distilled recommendation.

`handoff.json` contains `version`, `status: recommendation`, `goal`, `chosen_atom`,
`selection_reasoning`, `input_sha256`, `input`, `model_settings`, `evidence_directory`,
and `execution_authorized: false`. `chosen_atom` preserves the distillation verbatim,
including its completion condition and unresolved questions. Python exports it;
it does not attempt to infer factual completeness or approval from model wording.
This is a selector handoff, not a fabricated builder-admission packet.
