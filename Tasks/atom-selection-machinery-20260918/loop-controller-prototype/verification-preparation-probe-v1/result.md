# Verification-preparation prototype: passed

Astra medium selected the five historical tests unchanged. Python consumed that selection and ran ten separate PHPUnit processes: five against the committed delivery baseline’s relevant source boundary and five against the unchanged historical migration and reader.

- Baseline: 5/5 detected the missing migration, with no runtime setup error.
- Historical control: 5/5 passed against isolated SQLite using the currently installed dependencies.
- One model call; no answer corrections or test rewrites.
- Actual product checkout, untracked work and live loop state unchanged.

## Practical contribution

From a supplied historical source catalog and selected assignment, the prototype can choose reusable verification and execute it without the caller manually matching each case or rewriting tests. The red/green comparison establishes that the selected tests distinguish the current absence from the historical working capability.

## Boundaries

This is a retained standalone prototype, not an installed or connected builder upgrade. The caller supplied the source catalog and execution interface. The baseline root contains only the exact committed files needed for this isolated test, not a full application export. Historical cases are controlled examples, not production captures. SQLite tests do not establish MySQL compatibility, general PHP/application compatibility, delivery-branch restoration or final product completion. Other tables and every schema property are not covered by the tours-row assertions.

## Next integration point

Use this result in builder preparation to supply the test selection and executable verification, while retaining the separate assignment obligations for MySQL schema inspection, allowed diff and branch preservation. Do not count these successful historical-control tests as completion of the product atom.

## Evidence

`assessment.json` contains the untouched model choice and coverage limits. `result.json` records all ten executions and the retained-surface review. Each execution directory contains command, stdout, stderr and JUnit. `sources.json` binds the supplied source files. `input-state.json` records the commit, runtime and checkout fingerprints. The model call and response are preserved under `model/`.
