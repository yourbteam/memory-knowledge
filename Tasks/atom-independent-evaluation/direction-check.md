# Direction check — independent evaluation inputs

## Evidence

The canonical experiment runner sends each candidate's complete `outcome` object to the official evaluator. The retained self-scoring test's evaluator reads `outcome.correct` directly. The Development-Probe final validator separately sends the assembled candidate's complete result as both `execution_result` and `execution-result` evidence to the assessment adapter. In both paths, a producer conclusion can therefore become the official score or verdict without an independently observed fact.

## Verdict

The existing separation of candidate-reported metrics from official scores is sound but incomplete. The stable boundary is to keep candidate result bytes and their hash in the audit record while withholding the result object from official judges. Judges receive code-owned execution facts and hash-bound stdout, stderr, and telemetry references, and must ground a positive verdict in independently inspectable telemetry.

This verdict would flip only if candidate outcomes were themselves produced by a separate independent observer. They are written by the candidate adapter, so that condition is false.
