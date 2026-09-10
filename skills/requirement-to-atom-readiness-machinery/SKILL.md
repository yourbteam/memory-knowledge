---
name: requirement-to-atom-readiness-machinery
description: Determine whether source-linked requirements have enough evidence and resolved decisions to become implementation atoms. Use for evidence-bound readiness assessment, a blocked next action, or owner-approved sequential handoff; not for implementing atoms or granting consent or business authority.
---

# Requirement-to-Atom Readiness

Code owns identity, source admission, queue order, state, replay, readiness, and release.
Models answer bounded questions; they never approve a sequence or start implementation.

## Managed client installation

Both client installations expose these same instructions and public entrypoints. At launch,
the installed entrypoint verifies the installer's source record and the complete skill bytes,
then runs the canonical entrypoint with the same arguments. Repository-owned validators,
tests, and sealed-history source locations remain canonical; no dependency is copied or inferred.
Missing provenance or changed source bytes refuse before a work directory or model call is created.
Install and refresh both copies with the repository's managed installer, selecting this skill only.
This is a shared operator surface, not a second model backend: both currently use the existing
explicitly approved OpenAI Codex CLI interview contract. Installation grants no model-call approval.

## Start from declared evidence

Read `references/request-contract.md` for input and write boundaries, then use the current
`scripts/readiness_controller.py schema` and `--help` as the executable command contract.
Earlier atom-specific sections in references describe historical milestones, not current CLI availability.
Read `references/evidence-contract.md` and `references/graph-contract.md` when preparing evidence.
Use the additive Description and Requirements exporters; do not substitute loose documents for sealed handoffs.
Description wire version two carries the trusted producer hash and complete bound agreement
evidence for intent contracts two and three. Admission and frozen replay use the trusted producer's
pure completion verifier; never execute producer code supplied by a handoff. Contract three also
requires exact complete source passages. Legacy wire version one remains supported. These checks
establish evidence consistency, not independent semantic approval or whole-document coverage.
For a new assessment, use the code-owned invocation interview below. Do not hand-author the
request, contract role list, file hashes, or work path. The low-level `start REQUEST WORK
--expected-tip` interface remains available for existing integrations and captured-case verification.

## Prepare an invocation through code

Run `invocation-open SESSION`, where SESSION is a new absolute directory outside repositories,
Tasks, input source directories, and the intended runtime root. Its parent must already exist.
Code returns exactly one `next_question`, its answer schema, and a `ledger_tip`. The invoking model
answers that question from declared evidence using `invocation-answer SESSION QUESTION ANSWER_JSON
--expected-tip TIP`. ANSWER_JSON is a file containing only the answer value, not a request envelope.
Use `invocation-status SESSION` to resume; never guess the next question or reuse a stale tip.

Code asks for the feature, repository boundaries, sealed handoffs, evidence and authority records,
explicit model configuration and execution limits, then the authorized runtime root. It derives
the installed contract identities and hashes all supplied files itself. The runtime-root answer is
accepted only after the same complete direct, upstream and graph validation used by start. An
invalid answer leaves the same question available and creates no readiness run.

When all answers are recorded, run `invocation-prepare SESSION --expected-tip TIP`. Code returns
the frozen request, a generated disjoint run path, and the exact `invocation-start` command. Start
rechecks the input bytes and invokes the unchanged readiness startup. After launch, inspect status;
never retry a reserved, completed or failed launch as a new run. A changed input or installed code
requires a fresh interview. These commands make no semantic model calls and grant no business,
consent, implementation, or model-call authority.

Read `status WORK`, `advance WORK`, or `verify-replay WORK` before deciding what to do next.
Every mutation requires the exact returned ledger tip. Do not skip the queue head.
If mandatory evidence is missing, report the exact recovery condition; a model cannot replace the missing probe.

## Resolve one current item

Read `references/interview-contract.md` before preparing an interview or external question.
Use `prepare-external`, then the matching owner, evidence, or planning admission command.
Research and Plan are direct evidence tasks, not selectable skills.
For an eligible semantic item, use `prepare-interview`, then `prepare-launch` in a separate directory.
Show both frozen prompts and the plan to the owner. Only an explicit approval of those exact bytes
permits `launch-interview`; never manufacture authority from a model response or general build approval.
Preserve failed attempts. Follow only the launcher's declared timeout recovery; no manual extra calls.
The blocked-evidence canary and the eligible model-interview canary are separate cases.

## Produce the answer and hand off

Compile candidates only after the current evidence and planning obligations are resolved.
Use `compile-package` to obtain the immutable report and verdict. `blocked` and `needs_owner`
are useful resumable outcomes, never permission to implement.
Read `references/atom-handoff-contract.md` before approval or release.
Only exact owner sequence approval permits `approve-atoms` and `export-next-atom`.
Admit the prior atom's real completion proof before requesting a successor. A printed start-command
template is a handoff, not an instruction for this machinery to execute it.

## Validate the installation candidate

`scripts/run_canary.py run REQUEST NEW_OUTPUT` performs fresh upstream exports and the blocked path,
rechecks a separately completed real interview, and replays a declared all-green release history.
It runs the accumulated regression and captured-case suite. It makes no model calls and installs nothing.
Supply the explicit canary input fields declared by `FIELDS` in that script, including hash-bound
blocked input, source-snapshot map and requirements document, exact run paths, coverage and sequence
hashes, and the declared operator repository. Never replace those inputs with inferred evidence.
`scripts/run_canary.py verify REPORT` refuses failed, incomplete, changed or skipped-check evidence.
Activation eligibility is not owner approval, a new model review, or proof of a new implementation run.
Do not advertise a failed candidate as complete; retain the report and resolve its exact failed boundary.
