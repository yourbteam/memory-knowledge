# Direction check — case reference boundary

## Evidence

The retained telemetry finding was reproduced against the canonical Experiment Machinery paths: a repository-relative captured-case reference is resolved from the development manifest's parent in both the single-probe launcher and composition. Moving the same manifest changes the computed filesystem address even though the approved case identity and SHA-256 are unchanged. Atom Controller separately requires that manifest value to equal the approved `source_ref`, so changing it to an absolute runtime path breaks the approval identity.

## Verdict

The existing immutable-case approach is sound. The defect is the handoff contract: one manifest field is being used as both the approved logical reference and the runtime base-relative address. The stable boundary is an explicit source root plus an unchanged logical reference, with imported assembly inputs remaining hash-bound.

This verdict would flip only if development manifests were contractually fixed beside one repository root. The real machinery copies and nests them, so that condition is false.
