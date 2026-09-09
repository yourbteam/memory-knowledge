# Atom candidate handoff contract

Candidate compilation is opt-in. It neither executes atoms nor certifies readiness.

The retained direct Plan result is the sole candidate source. Each candidate carries
the current eight Atom Building request fields and requirement, prerequisite atom,
verification, owner-decision and evidence identities. The published candidate schema
is the direct Plan response schema, including its immutable action identity.

`prepare-candidates WORK --expected-tip TIP` validates the whole current candidate
set before it creates any cohesion interview. Code rejects missing requirement or
case mappings, unknown/self/cyclic prerequisites, unresolved queue entries, unfit
evidence, unresolved owner decisions, ambiguous repositories, paths outside declared
boundaries, unfrozen case bytes, and downstream contract drift. Downstream validation
uses the installed Atom Controller bound to its declared source; supplied code is
never executed. Validation-shape source files must already be frozen evidence and
must still match the target repository. Render requests require no shape-source reads.

Verification is not a candidate producer assertion. Each referenced verification
must have its own admitted two-seat adequate assessment, independent route, complete
captured success and rejection cases, and requirement edges. The evidence importer
starts verification declarations blocked. Future-system design adequacy is distinct
from proof that the future implementation has already been built.

`prepare-interview` then asks two blind seats whether the next candidate expresses
one independently testable outcome with complete prerequisites and no second hidden
duty. Both receive the entire exact candidate and registered source bytes. The
existing prepare-launch/launch-interview authorization boundary still applies.
Preparation alone authorizes no transmission. Response identities, evidence quotes,
complete requirement IDs, agreement and attempt budget are checked by code. A fact
is bound to the full candidate hash, including scope, cases and dependency mappings.

`compile-candidates WORK --expected-tip TIP` rechecks all inputs and refuses unless
every candidate has exactly one matching cohesive fact. It orders prerequisites
before dependents with lexical tie-breaking, strips readiness wrapper fields, and
writes canonical UTF-8 JSON plus one newline. Request and sequence hashes are retained
in the same append-only transaction as the generated files. Replay rederives them.
Owner corrections invalidate candidate preparation and compilation along with their
dependent facts; immutable historical evidence is never rewritten.

## Independent verification plan for this atom

Success proof: feed an actual retained Plan result through the public preparation,
two-seat interview admission, compilation and replay commands. Independently inspect
the emitted request bytes using the actual downstream validator; compare every
downstream field with its frozen candidate and prove prerequisite ordering and
byte-stable repeated derivation. Public readiness must remain not-assessed and no
Atom Building start command may be executed.

Rejection proof: separately mutate missing scope/case/requirement mappings, a foreign
or cyclic prerequisite, unfit or drifted source evidence, unresolved owner decisions,
producer-only verification, absent/disagreeing/must-split cohesion seats, changed
candidate bytes after an old judgment, stale ledger tips and tampered output files.
Inspect raw exit status, immutable ledger and emitted-file membership rather than
trusting a producer pass/fail report. A failed preparation/compilation must emit no
partial transaction; a malformed interview remains retained without admission.

An independent experiment evaluator receives raw command outputs, not candidate
scores. Its positive and negative calibrations must pass before comparison. Final
confirmation repeats the same public commands against promoted canonical code.
Controlled mutations exercise rejection mechanics; they are never presented as new
semantic judgments or evidence that a real feature is satisfied.

## Approval and sequential release

`approve-atoms WORK SUBMISSION --expected-tip TIP` accepts exactly schema_version 1,
atom_sequence_sha256, decision (`approved` or `rejected`), and owner_record (absolute
path plus SHA-256). The referenced owner file must contain exactly schema_version,
atom_sequence_sha256 and decision, matching the submission. This is the trusted
operator-input boundary, not human authentication: models must not author or submit
owner decisions. Tests use explicitly labeled controlled operator inputs only.

Approval requires the current ready package and exact sequence. The transaction
captures the owner bytes; replay never rereads their origin. It then builds a new
immutable package containing approval.json. An interrupted or failed generation
does not grant release authority. Existing unapproved generations remain unchanged.
Changed evidence or candidates require a new run; released sequences cannot be
reapproved. A rejected sequence can receive a new exact owner decision before release.

`export-next-atom WORK --expected-tip TIP` chooses the next ordinal internally,
publishes only that request and its hash-bound receipt under WORK/handoff, and returns
a start-command argument template without executing it. It never accepts an ordinal
from the caller. Every handoff is verified against the journal on replay. An
interrupted handoff publication remains visibly refused rather than being reused.

Before the next release, `admit-atom-completion WORK SUBMISSION --expected-tip TIP`
requires exactly `{"atom_run":"/absolute/completed/run"}`. The run must be inside
the declared working root or a declared target repository. The installed, source-bound
Atom Controller alone runs `authorize-next`. Open supersession chains are refused
before invoking that command, because closing such a chain belongs to Atom Building.
The released request must match the complete preserved build request, not just its
atom name; serialization differences between the two controllers are accounted for
by verifying both the released canonical hash and the downstream original-byte hash.
The response, source hash, request and ledger bytes are captured. Replay validates
those snapshots without rerunning an old external decision. Immediately before
successor export, the same live authorization must return the identical proof and
blocker-closeout identity. Incomplete builds, open blockers, changed proof, stale
approval and skipped atoms cannot release a successor. Completion does not start,
modify or certify an implementation; it consumes the existing builder's result.
