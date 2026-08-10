# Chain ledger — the description machinery

Name settled by Kamen, 10 August 2026: **description machinery**.

Goal: whatever already exists that says something about a subject becomes one description of that
subject which the requirements machinery can consume without a person rewriting it first. The
material differs every time — code, logs, a conversation, notes left by an earlier run — and the
output is always the same one document.

What it takes in, settled with Kamen on 10 August 2026:

- **An intent**, always — what needs to be done or achieved, in the owner's words.
- **Context**, when any exists — code, logs, records, notes left by an earlier run, a conversation.

The machinery holds a fixed set of questions a description must answer. It looks for each answer in
the context first and quotes what it finds; whatever the context does not answer, it asks the
operator, and the answer is quoted the same way. Nothing is filled in by guessing, and every line of
the finished document points at either something in the context or something the operator said.
Greenfield is simply the case where the context answers nothing and every question goes to a person.

Two real subjects exist, and both are the test:

1. **The one that worked.** The phase-58 description was written by hand and the requirements
   machinery consumed it, producing 142 requirements still to build. That is the shape to reach.
2. **The one that does not yet work.** Twenty-three observations collected from the notes builders
   wrote while making requirements true. They are quoted exactly, which is honest, and they are
   statements rather than requirements — "eight tests already fail" is not something anybody can
   make true. A builder handed one refused it, correctly.

Distance, one number, never redefined: **of the observations that go in, how many come out of the
requirements machinery as an accepted requirement with a check somebody else can run.** Read from
the requirements machinery's own document, not from this one. It starts at zero of twenty-three.

The division is the same as the other two machineries: code fixes what gets looked at and judges
nothing; a model judges what things mean; two readers who cannot see each other, and agreement or
nothing. What is new here is the question — not "is this true of the built system" but "is this
sayable in a way the next machinery can work from".

| # | what failed | what was fixed | proof | distance | cost to find |
| --- | --- | --- | --- | --- | --- |
