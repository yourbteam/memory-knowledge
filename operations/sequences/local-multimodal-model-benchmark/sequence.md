# local-multimodal-model-benchmark

## Use When

Benchmark a local multimodal model against image-based cases and persist comparable immutable evidence.

## Outcome

Run a specified local multimodal model against specified image cases and persist immutable, schema-validated evidence while preserving every pre-existing local model and any separate thinking channel returned by the model.

## Required Inputs

- A local multimodal model name served by a loopback Ollama-compatible endpoint.
- One or more benchmark cases, each with a purpose prompt, absolute source image paths, and a JSON response schema.
- An immutable evidence output path, pull authorization, explicit enabled-or-disabled thinking mode, timeout, and model runtime options.

## Commands

| step | command or action | result | correction or note |
| --- | --- | --- | --- |
| run-benchmark | python3 scripts/local_multimodal_model_benchmark.py | One immutable benchmark evidence artifact is written and every pre-existing local model remains installed. | Code validates the spec, source hashes, response schema, output immutability, loopback endpoint, and preservation of pre-existing models. |
| verify-automation | python3 scripts/verify_local_multimodal_model_benchmark.py | Returns ok true after the runner and semantic-adapter tests pass. | Verifier proves the general runner and code-controlled intake contracts without requiring a live model download. |
| record-correction | python3 scripts/work_memory.py correct --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after selected-bundle drift | Use only when the selected controller remains unchanged. |
| record-protected-correction | python3 scripts/work_memory_bootstrap.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required after protected selected-bundle drift | Use the activated sealed controller through the canonical guard. |
| launch-protected-correction | python3 scripts/work_memory_bootstrap_launcher.py correct --task-id <task-id> --run-id <run-id> --blocker-id <blocker-id> --occurrence-id <occurrence-id> --step-id <step-id> --changed-artifact <path> --solution <solution> --reusable-behavior-changed yes | required when the lifecycle controller selects sealed execution | The lifecycle controller constructs this command; operators do not improvise it. |
| transition-corrected-blocker | python3 scripts/blocker_catalog.py transition --run-id <run-id> --blocker-id <blocker-id> --to-status fixed-awaiting-verification | required after a non-atomic correction | Run only after the correction event and bundle transition are durable. |
| close-corrected-predecessor | python3 scripts/work_memory.py run-close --run-id <run-id> --result failed | required after every blocker is fixed-awaiting-verification | The corrected bundle must be verified by a fresh bound successor. |

## Failure Handling

Stop on validation, API, pull, schema, or preservation failure and retain non-overwritten failure evidence with the raw model response and separate thinking channel when available.

## Verification

- Run the no-argument verifier twice against the exact source bundle, then run the promoted no-argument benchmark launcher through registered shared intake and validate its immutable evidence.

Pass signal: Benchmark runner writes one immutable schema-valid evidence artifact and preserves all pre-existing local models.

Promoted from `2026-08-16-local-multimodal-model-benchmark`. The prior discovery evidence is historical; run a fresh
registered same-path verification before treating it as current-bundle proof.
