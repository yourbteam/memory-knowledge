# Atomic Prototype Development: Process and Contract

## Purpose

Atomic prototype development is the method used to build machinery whose final design cannot be
known safely in advance. The complete practical goal is agreed first, but the implementation is
not divided into a speculative roadmap. Instead, one small, useful capability is selected from the
current evidence, built through the real path, judged, and either retained or corrected. Only a
proven win may expose and justify the next atomic step.

The method exists to prevent two expensive failures:

1. building a large design from assumptions before the real case reveals what is needed; and
2. spending time on infrastructure that is technically elaborate but does not move the practical
   goal.

## The governing idea

The overall step has a stable goal. The route to it is adaptive.

- **The goal is fixed enough to judge progress.** It names what the operator must be able to do
  when the step is complete and where this step must stop.
- **The next atom is not selected from a prewritten milestone list.** It is selected from the
  earliest currently observed gap between proven behavior and the goal.
- **Each atom must add practical value.** After it wins, the machinery must be able to do something
  useful that it could not reliably do before.
- **Evidence selects the next atom.** Estimates and possible future atoms may be discussed, but
  they are not commitments and do not authorize implementation.

For Info Intake Machinery, the first-layer goal established the boundary: preserve supplied
information as immutable sources, create AI-readable projections with complete audit lineage,
preserve failures and unreadable units instead of overwriting them, obtain necessary operator
input through preserved follow-up sources, and stop at the agreed first-layer terminal boundary.
Later interpretation or use of the information was not allowed to pull the work beyond that
boundary.

## Definitions

### Overall step or layer

A complete operator-meaningful outcome containing several capabilities. It has a practical
terminal condition, not merely a list of components.

### Atomic step

The smallest independently testable capability that removes one observed obstacle to the overall
step goal. It must be meaningful in the real workflow, not merely small in code size.

An atomic step is valid only when all of these are true:

- one behavior becomes separately true or false;
- the behavior is required by the overall step goal;
- its need is grounded in current real-path evidence;
- its contribution can be explained in operator terms;
- its code-versus-model ownership can be decided explicitly;
- a bounded prototype can prove or disprove it; and
- its success does not depend on pretending later unbuilt capabilities already exist.

### Prototype

A bounded implementation attempt used to test one hypothesis about the current atomic step. A
prototype is not disposable by definition: proven product code is retained. Unproven or irrelevant
mechanisms are revised or removed.

### Win

An atomic step is a win only when the intended practical behavior has been exercised through the
real path, its relevant refusal or failure boundary has also been tested, the evidence supports the
hypothesis, and the result is accepted as moving the agreed goal. Passing tests of internal
mechanisms alone is not a win.

## Responsibilities

### The owner/operator

The owner:

- approves the overall step goal and its stopping boundary;
- approves the bounded envelope for an atomic implementation;
- supplies owner decisions or missing real inputs that machinery cannot infer legitimately;
- judges whether demonstrated behavior is practically valuable; and
- separately authorizes commits, pushes, deployments, destructive actions, credentials, or scope
  expansions.

Approval of one atom is not approval of a speculative chain of later atoms.

### The implementation controller

The controller:

- keeps the overall goal and stopping boundary visible;
- inventories what is already proven and what remains unproven;
- recommends the next atom from the earliest practical gap;
- explains how that atom connects to the retained behavior and moves the goal;
- decides which responsibilities belong to deterministic code and which require model reasoning;
- freezes the implementation envelope before editing;
- runs and observes the real path;
- gives the prototype a clear verdict;
- retains only proven, in-scope code; and
- recommends the next atom only after the current atom is a win.

The controller may use bounded research, planning, implementation, or review assistance for one
observed question. That assistance cannot take control of the lifecycle, widen the scope, or create
an implementation roadmap.

## The atomic development loop

### 1. Restate the practical step goal

Before selecting an atom, state:

- what the operator will be able to accomplish when the overall step is complete;
- what evidence will show completion; and
- what later concern is explicitly outside this step.

This prevents a technically related concern from silently becoming part of the current build.

### 2. Inventory the proven state

Inspect the current real path and separate:

- behavior proven through actual use;
- behavior present in code but not proven through the operator path;
- the earliest missing behavior that blocks the goal; and
- later gaps that are real but not yet the next constraint.

The inventory reports progress; it does not convert every known gap into an approved roadmap.

### 3. Define one candidate atom

The proposed atom must answer five questions in plain language:

1. **What new practical behavior will exist?**
2. **What current evidence shows it is the next constraint?**
3. **How does it connect to the last proven capability?**
4. **How does it move the overall step goal?**
5. **What is deliberately excluded?**

If the proposal can only be justified as “needed plumbing,” it is not yet grounded. Plumbing can
become a valid atom only when the real path shows that its absence is the earliest blocker and the
prototype proves the downstream behavior it enables.

### 4. Decide code and model ownership

Ownership is chosen per atomic behavior, not per component or file.

Use deterministic code for anything that must be exact, repeatable, enforceable, or auditable,
including:

- identities, hashes, ordering, and state transitions;
- immutable source and answer preservation;
- enums and allowed response types;
- interview sequencing and one-question-at-a-time presentation;
- coordinate, schema, lineage, and completeness validation;
- replay, resume, terminal conditions, and refusal behavior;
- canonical assembly; and
- ensuring every required unit receives an explicit outcome.

Use a model where meaning must be interpreted, including:

- visual or semantic reading;
- deciding whether two records represent the same meaningful unit;
- identifying purpose-relevant content;
- reasoning about visible relationships;
- formulating a focused human question; and
- assessing whether new information resolves a stated semantic gap.

When model reasoning must end in a fixed set of answers, prompting is not enforcement. Code must
present the exact permitted values, accept only one of them, reject anything else without
advancing, and preserve the rejected and accepted attempts. Free text is accepted only where the
task genuinely requires open semantic content, and code still binds it to the exact question,
source, or gap.

The rule is: **models judge meaning; code controls the contract around that judgment.**

### 5. Freeze the prototype envelope

No implementation starts until the owner approves a compact envelope containing:

- **Outcome:** the one practical behavior to make true;
- **Stopping condition:** the exact proof that ends this atom;
- **Allowed scope:** repositories, paths, and existing machinery that may change;
- **Real evidence:** captured success and failure cases available for proof;
- **Budget:** maximum elapsed time or prototype attempts; and
- **Exclusions:** commits, pushes, deployments, destructive actions, credentials, external
  messages, unrelated assessment, and any other non-authorized work.

The envelope authorizes adaptive work only inside its stated outcome. A newly discovered need that
changes the outcome or materially widens the scope requires a new envelope.

### 6. Run Prototype 0

Prototype 0 exercises the current production path before a broad design is written. Its purpose is
to reproduce, characterize, or directly prove the current behavior using captured real inputs.

Prototype 0 identifies the earliest deviation and traces:

1. what produced the relevant input or decision;
2. what state or evidence was persisted; and
3. what downstream consumer did with it.

This cause chain determines whether the next change belongs at the visible failure, an upstream
contract, or the underlying architecture. It prevents a garden of special cases around symptoms.

### 7. Build the smallest deciding delta

For the active prototype, record:

- **Hypothesis:** why this small change should produce the practical behavior;
- **Delta:** the smallest product-code change capable of testing it;
- **Proof:** the real-path result that would confirm it;
- **Refutation:** the result that would disprove it; and
- **Remaining gap:** what will still be unproven even if it succeeds.

The delta should use general properties of the input and workflow. A rule inferred from one example
must not be hardcoded as an exception for that image, annotation style, spreadsheet, repository,
domain, color, or layout. The example supplies evidence; it does not define the general rule.

### 8. Exercise the real path

The prototype is run through the path the operator will actually use, with the real source when it
is available. Synthetic fixtures may isolate mechanics, but they cannot replace the captured case
as the deciding proof.

The proof must normally cover:

- the practical success behavior;
- the relevant refusal, ambiguity, or failure behavior;
- preservation and replay when the capability is stateful;
- no silent overwrite or loss of prior evidence; and
- the system-level answer or outcome produced by the mechanism.

A test showing that a helper ran, an event was written, or a new field exists does not prove the
operator outcome.

### 9. Give exactly one verdict

Each prototype receives one verdict:

- **Promote:** the hypothesis held. Retain the proven code and identify the remaining practical
  gap.
- **Revise:** the goal and atom remain correct, but evidence disproved the mechanism. Correct or
  remove the failed mechanism and test the same atom again.
- **Discard:** the mechanism or atom does not serve the approved outcome. Remove it rather than
  carrying it forward as infrastructure.

A failure does not automatically justify another patch. First determine whether it is a real
defect in a sound approach or evidence that the approach itself cannot reach the goal.

### 10. Declare the atom a win—or stay on it

The next atom is not selected while the current atom is merely implemented, partially tested, or
promising. The current atom must first have:

- a promoted prototype;
- real-path evidence;
- a clear statement of what the operator can now do;
- no unresolved defect inside the atom's own promised behavior; and
- owner acceptance that this is a practical win.

If these conditions are not met, the work remains on the same atom or the approach is changed. It
does not advance to hide the incompleteness behind another layer.

### 11. Select the next atom from new evidence

After a win, take inventory again. The retained behavior changes what is now observable, and that
new evidence identifies the next earliest gap. The next atom must again be justified, allocated
between code and model, bounded, approved, prototyped, and judged.

## Anti-drift contract

The method is being followed only while all of these remain true:

- Every active change names the practical operator behavior it enables.
- The work is still inside the agreed layer boundary.
- The active atom is the earliest observed constraint, not an interesting adjacent problem.
- Internal machinery work is retained only when its downstream practical outcome is proven.
- Model instructions are not treated as enforcement where code can constrain the answer.
- Real examples ground general rules but do not become hardcoded exceptions.
- A prototype does not silently expand into a new controller, sequence, framework, or package.
- Failures are traced to the stable contract or architecture boundary before fixing them.
- Commits and pushes occur only under separate explicit authorization.
- The next atom is derived only after the current one wins.

Warning signs of drift include:

- reporting files, tests, events, adapters, or registrations as progress without a new usable
  behavior;
- repeatedly fixing execution machinery while the goal's practical measure does not move;
- creating generalized infrastructure before the real path requires it;
- proving only the mechanism and not the answer it causes;
- treating a candidate future atom as committed work;
- widening from the current layer into later assessment or optimization; and
- describing sunk time or complexity as evidence that an artifact is valuable.

When a warning sign appears, the correct response is to compare the work with the overall goal,
identify what practical behavior actually moved, and discard or re-bound anything that did not.

## How progress is reported

After each atom, the report should state:

1. what the machinery can now do through the real path;
2. what evidence proved it;
3. the prototype verdict;
4. what remains between the proven state and the overall step goal; and
5. why the recommended next atom is now the earliest useful addition.

An estimate of remaining atoms is explicitly approximate. Because later evidence is intentionally
allowed to change the route, the estimate is not a promise or roadmap.

## Completion contract for the overall step

The overall step is complete only when:

- the agreed operator-visible behavior works end to end;
- all required sources, decisions, and outcomes have the promised audit lineage;
- relevant failure and unreadable cases stop safely and visibly;
- resume and replay preserve prior evidence where the workflow is stateful;
- no discarded experiment remains in the product surface;
- the accumulated retained changes have been reviewed together; and
- one final confirmation succeeds through the same entry path the operator will use.

Completion is not inferred from the number of atoms, elapsed days, amount of code, or amount of
money spent.

## Worked examples from Info Intake Machinery

### Deterministic spatial traversal

**Observed gap:** a model looking at a whole annotated image could claim completion while silently
missing areas.

**Atomic capability:** code divides the source into deterministic regions, visits them in fixed
order, and requires one outcome for every region. The model identifies purpose-relevant content or
an explicit gap inside the active region. Code validates ownership and prevents completion while a
region lacks an outcome.

**Why the split was correct:** deciding what visible content means requires a model; proving that
every region was visited and received an outcome requires code.

**Practical movement:** the readable projection could no longer finish on a model's unsupported
global assurance of completeness.

### One-question-at-a-time operator interview

**Observed gap:** asking one known question per model pass was slow, but showing the operator every
known question at once was burdensome.

**Atomic capability:** a model composes the complete currently known question set in one pass.
Code binds each question to its exact gap, persists the complete round, presents only the first
unanswered question, stores the answer as a new immutable source, and then presents the next.

**Why the split was correct:** question wording requires semantic reasoning; completeness,
ordering, response type, one-at-a-time presentation, and persistence require code.

**Practical movement:** the operator receives a manageable interview without paying for a separate
model discovery pass for every already-known question.

## Compact reusable contract

Before building an atom, record:

```text
Overall step goal:
Current proven behavior:
Earliest practical gap:

Atomic outcome:
Connection to last win:
Contribution to overall goal:
Excluded concerns:

Code owns:
Model owns:
Code-controlled model answer contract:

Real success case:
Real failure or refusal case:
Deciding proof:

Allowed repositories and paths:
Maximum time or prototype attempts:
Excluded actions:
Owner approval:
```

After the prototype, record:

```text
Observed practical outcome:
Real-path evidence:
Verdict: promote | revise | discard
What is now proven:
What remains unproven:
Owner win decision:
```

Only a promoted and accepted win returns the process to inventory and selection of the next atom.
