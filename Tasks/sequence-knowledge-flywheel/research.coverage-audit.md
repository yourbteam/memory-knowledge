# Sequence Knowledge Flywheel — Requirements Coverage Audit

## Frozen scope

Coverage is limited to R1-R12 in `research.md`. New product outcomes, generic
subsystems, other repositories, directive/corpus changes, live retirement apply,
commits, pushes, and deployments are excluded.

## Assessment 1

Verdict: GAPS.

| gap | requirement | omission | bounded closure | status |
| --- | --- | --- | --- | --- |
| RCG-001 | R10 | v1 refusal existed but explicit v2 upgrade path did not | logical-retire legacy provenance, then complete v2 capture; refuse held/target conflicts | fixed-awaiting-fresh-assessment |
| RCG-002 | R11 | retirement plan/apply lacked one lock and lost-response plan replay | shared retirement lock, same-output identical-snapshot replay, contention fixtures | fixed-awaiting-fresh-assessment |
| RCG-003 | R12 | requirement said redaction although design rejects secrets and stores result hashes | align requirement to recursive rejection and hash-only result persistence | fixed-awaiting-fresh-assessment |

R1-R9 were fully covered. R4/R5 auto-drive versus R11 human approval, R3 dedupe
versus R8 retirement, and R8 retirement versus R10 exact-path resume were reconciled.

## Parent closures

- `research.md` now defines only the existing-mechanism v1 upgrade and its negative/positive fixtures.
- Retirement planning and apply share one exact lock/replay contract with contention tests.
- R12 now names the actual secret-rejection and hash-only evidence behavior traced by AC3/AC7.

A fresh no-edit coverage reassessment is required.

## Assessment 2

Verdict: PASS. Assessed `research.md` SHA-256:
`495234f62caa6890ddcdb3f2cc462767cc8e258ab072b328a689bf732ce80ff7`.

RCG-001 through RCG-003 are closed. The fresh assessor found every R1-R12
requirement, decomposed subcase, mechanism, conflict reconciliation, and acceptance
proof covered, with no new outcome. Coverage convergence is complete.
