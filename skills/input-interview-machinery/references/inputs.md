# Input files

Each caller owns its reusable template. Every question states what the downstream consumer
needs the answer for. Python snapshots the template for each run; edit the template, not a run.

```json
{"id":"my-interview","questions":[{"id":"scope","text":"Which decision needs resolving?","consumer_use":"Bound the next implementation decision to the owner's goal."}]}
```

Context is a JSON object with exactly one source list per question ID. Use actual source text;
source IDs identify supporting quotes. Include the information the interviewed model needs,
not merely the question or an assessor's summary of it.

```json
{"scope":[{"id":"owner-request","text":"The actual owner request goes here."}]}
```

Replies preserve user wording or additional source evidence:

```json
{"origin":"user","text":"The owner's exact answer or correction.","sources":[]}
```

For retrieved evidence use `origin: "source"` and `sources: [{"id":"...","text":"..."}]`.
An explicit stop uses the user format; do not classify stop by keyword matching.

## Template and model editing

All operations use the same entry point; `QUESTION.json` is one question object and
`ORDER.json` is an array of every question ID in the intended order.

```sh
python3 <skill-dir>/scripts/input_interview.py configure create --file TEMPLATE.json --id NAME
python3 <skill-dir>/scripts/input_interview.py configure add --file TEMPLATE.json --question QUESTION.json
python3 <skill-dir>/scripts/input_interview.py configure show --file TEMPLATE.json
python3 <skill-dir>/scripts/input_interview.py configure edit --file TEMPLATE.json --id ID --question QUESTION.json
python3 <skill-dir>/scripts/input_interview.py configure remove --file TEMPLATE.json --id ID
python3 <skill-dir>/scripts/input_interview.py configure reorder --file TEMPLATE.json --order ORDER.json
python3 <skill-dir>/scripts/input_interview.py configure model --file SETTINGS.json --provider codex --model gpt-5.5 --reasoning high
```

Changing settings affects new runs only. Use a model/reasoning combination supported by the
authenticated CLI. Fixed lens prompts live in `scripts/lenses.json`; the validated order is
connections, conditions, support, use, consistency, unanswered-dependencies, decision-boundary,
exact-relationship.

The handoff preserves original questions, effective questions after corrections, final answers,
source quotations, limitations, follow-up history, revisions, model settings, and unresolved IDs.
Check `status` before treating the output as completed. Keep the run directory for audit.
