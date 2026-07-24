# Planner handoff — deterministic sequence intake

Plan the implementation from
[`research.md`](research.md) as a cross-repository migration, not as an extension of the
generic argv collector.

The first deliverable must establish the stable boundary in `memory-knowledge`:

1. replace operator-visible `argv` collection with semantic-field schemas plus deterministic
   sequence adapters;
2. reject schemas that ask for command syntax;
3. add a registry keyed by all 27 canonical sequence identities;
4. make no-argument preparation side-effect free and keep dispatch authorization separate;
5. prove the contract with golden payload and forbidden-schema tests.

Subsequent repository slices must migrate exact entrypoints and callers listed in the research,
including the six commit/push modes, all deployment paths, generated user-admin commands,
sequence documents, and both source and installed sequence-runner skills.

Do not plan implementation of `taggable-admin-spa-deploy` until its authoritative repository and
script are resolved. Do not wrap `judge_ollama.py` or `test_engine_upgrades.py` in operator intake;
test their bounded exception contracts instead.

No commit, push, deploy, auth mutation, database operation, container recreation, cleanup, or
live workflow drive is authorized by this handoff.
