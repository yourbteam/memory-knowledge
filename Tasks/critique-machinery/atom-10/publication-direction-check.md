# Publication direction check

The publisher found trailing spaces in the three live `reader-prompt.txt` evidence files. This is
the same evidence-publication class closed in Atom A: diagnostic bytes are valid evidence but fail
the repository's ordinary source-code whitespace screen.

## Path 1 — alter the evidence

Trimming the prompts would make the generic check pass, but it would change the exact bytes that
reached the seats and contradict the handover's immutable-evidence boundary. This path is rejected.

## Path 2 — preserve evidence under a path-local Git policy

The established Atom A mechanism disables whitespace diagnostics only for the named raw evidence
filename below its evidence directory. Code, specifications, receipts, and every other file retain
the normal check. This path preserves the live input bytes and lets the publisher inspect the rest
of the atom normally. This path is selected.

The verdict would flip only if the prompt bytes were not evidence of the exact live seat input.
They are: each attempt receipt binds its instruction hash to that persisted prompt.
